"""
Client for the FooQt remote scan agent (Zed-remote style).

When a library dir is an sftp:// path, instead of walking the tree over SFTP
(one round-trip per stat/listdir + a full download of every file just to read
tags), we run a tiny stdlib-only agent ON the remote host:

  * on first use we probe 127.0.0.1:45601..45610 on the remote host through an
    SSH direct-tcpip channel (so nothing is exposed on the network)
  * if the agent is not there, we install remote_agent.py to
    ~/.local/lib/fooqt/remote_agent.py over SFTP and start it via SSH
  * if the agent responds but reports an older/different VERSION, we re-upload
    the file and restart it (auto-update over SSH)
  * scans run locally on the remote host; the client polls /progress and
    incrementally syncs new folders/tracks into the local DB
"""

import json
import logging
import os
import posixpath
import re
import secrets
import shlex
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

import sftp as sftp_mod
from virtualfs import is_sftp_path, parse_sftp_url

# Agent discovery intentionally probes closed ports; silence paramiko's
# "Secsh channel N open FAILED: Connection refused" warnings.
logging.getLogger("paramiko").setLevel(logging.ERROR)

AGENT_PORT = 45601
PORT_SPAN = 10
REMOTE_DIR = ".local/lib/fooqt"
AGENT_FILENAME = "remote_agent.py"
POLL_INTERVAL = 1.5
STREAM_CHUNK = 256 * 1024


class RemoteError(Exception):
    pass


def _agent_source_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), AGENT_FILENAME)


def _local_agent_version():
    """Version the client expects, read from the bundled agent source."""
    try:
        with open(_agent_source_path()) as f:
            head = f.read(4096)
        match = re.search(r'^VERSION\s*=\s*"([^"]+)"', head, re.M)
        return match.group(1) if match else "0"
    except OSError:
        return None


class RemoteClient:
    """One remote host: agent lifecycle + JSON/HTTP requests over SSH."""

    def __init__(self, hostname):
        self.hostname = hostname
        self._port = None
        self._token = None
        self._lock = threading.RLock()

    # ---- low-level plumbing ------------------------------------------------

    def _ssh_client(self):
        conn = sftp_mod.get_sftp_manager().get_connection(self.hostname)
        conn.ensure_connected()
        if not conn.client:
            raise RemoteError("no SSH connection to %s" % self.hostname)
        return conn.client

    def _sftp(self):
        conn = sftp_mod.get_sftp_manager().get_connection(self.hostname)
        return conn.ensure_connected()

    def _http(self, method, path, port, body=None, token=None, timeout=10):
        """One-shot HTTP request over an SSH direct-tcpip channel."""
        transport = self._ssh_client().get_transport()
        if transport is None or not transport.is_active():
            raise RemoteError("SSH transport to %s is not active" % self.hostname)
        chan = transport.open_channel(
            "direct-tcpip", ("127.0.0.1", port), ("localhost", 0), timeout=timeout
        )
        try:
            chan.settimeout(timeout)
            lines = [
                "%s %s HTTP/1.1" % (method, path),
                "Host: 127.0.0.1",
                "Connection: close",
                "Accept: application/json",
            ]
            if token:
                lines.append("X-Fooqt-Token: %s" % token)
            payload = None
            if body is not None:
                payload = json.dumps(body).encode("utf-8")
                lines.append("Content-Type: application/json")
                lines.append("Content-Length: %d" % len(payload))
            request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")
            chan.sendall(request if payload is None else request + payload)

            buf = b""
            while True:
                chunk = chan.recv(65536)
                if not chunk:
                    break
                buf += chunk
            head, _, raw_body = buf.partition(b"\r\n\r\n")
            status_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            status = int(status_line.split(" ")[1])
            data = None
            if raw_body:
                try:
                    data = json.loads(raw_body.decode("utf-8"))
                except ValueError:
                    data = None
            return status, data
        finally:
            try:
                chan.close()
            except Exception:
                pass

    def _exec(self, cmd, timeout=20):
        """Run a command on the remote host through a POSIX shell.

        The explicit `sh -c` wrapper matters: login shells like csh/tcsh do
        not understand `VAR=value cmd` or `command -v`."""
        client = self._ssh_client()
        try:
            _, stdout, _ = client.exec_command(
                "sh -c %s" % shlex.quote(cmd), timeout=timeout
            )
            out = stdout.read().decode("utf-8", "replace")
            try:
                stdout.channel.recv_exit_status()
            except Exception:
                pass
        except Exception as e:
            # str() of some paramiko/socket exceptions is empty -> use repr
            raise RemoteError(
                "remote command failed (%r): %s" % (e, cmd[:80])
            )
        return out

    # ---- discovery / install / lifecycle ------------------------------------

    def ping(self, port, timeout=3):
        try:
            status, data = self._http("GET", "/ping", port, timeout=timeout)
            return data if status == 200 and data else None
        except Exception:
            return None

    def _probe(self):
        """Find a running agent; returns (port, ping_info) or None."""
        for port in range(AGENT_PORT, AGENT_PORT + PORT_SPAN):
            info = self.ping(port)
            if info:
                return port, info
        return None

    def _remote_paths(self):
        home = self._sftp().normalize(".")
        state_dir = posixpath.join(home, REMOTE_DIR)
        return (
            state_dir,
            posixpath.join(state_dir, AGENT_FILENAME),
            posixpath.join(state_dir, ".token"),
        )

    def _mkdirs(self, sftp, remote_dir):
        current = "/"
        for part in remote_dir.strip("/").split("/"):
            current = posixpath.join(current, part)
            try:
                sftp.stat(current)
            except OSError:
                try:
                    sftp.mkdir(current)
                except OSError:
                    pass

    def _install(self):
        source = _agent_source_path()
        if not os.path.exists(source):
            raise RemoteError("agent source is missing: %s" % source)
        sftp = self._sftp()
        state_dir, agent_path, _ = self._remote_paths()
        self._mkdirs(sftp, state_dir)
        sftp.put(source, agent_path)

    def _find_python(self):
        out = self._exec("command -v python3 || command -v python", timeout=10).strip()
        python = out.splitlines()[-1].strip() if out else ""
        if not python:
            raise RemoteError("no python interpreter found on %s" % self.hostname)
        return python

    def _kill(self):
        try:
            self._exec("pkill -f %s || true" % shlex.quote(AGENT_FILENAME))
        except Exception:
            pass

    def _start(self):
        token = secrets.token_hex(16)
        python = self._find_python()
        state_dir, agent_path, _ = self._remote_paths()
        agent_log = posixpath.join(state_dir, "agent.log")
        # NOTE: `cd DIR; nohup ... &` - the backgrounded command must be a
        # SIMPLE command. With `cd DIR && nohup ... &` the shell keeps an
        # intermediate subshell that inherits (and holds open) the exec
        # channel's stdout while it waits on the never-exiting agent, so
        # stdout.read() on the SSH channel never reaches EOF.
        cmd = (
            "cd %s; FOOQT_REMOTE_TOKEN=%s nohup %s %s --port %d --state-dir %s "
            "</dev/null >> %s 2>&1 & echo started"
        ) % (
            shlex.quote(state_dir),
            token,
            shlex.quote(python),
            shlex.quote(agent_path),
            AGENT_PORT,
            shlex.quote(state_dir),
            shlex.quote(agent_log),
        )
        self._exec(cmd)

        deadline = time.time() + 15
        while time.time() < deadline:
            found = self._probe()
            if found:
                self._port, _ = found
                self._token = token
                return
            time.sleep(0.4)
        # surface the agent's own startup errors instead of a bare timeout
        tail = ""
        try:
            tail = self._exec(
                "tail -n 5 %s 2>/dev/null" % shlex.quote(agent_log), timeout=10
            ).strip()
        except Exception:
            pass
        raise RemoteError(
            "agent did not come up on %s%s"
            % (self.hostname, ("; agent.log tail: " + tail) if tail else "")
        )

    def _load_token(self):
        """Read the token file written by a previously started agent."""
        try:
            with self._sftp().open(self._remote_paths()[2], "rb") as f:
                return f.read().decode("utf-8", "replace").strip()
        except Exception:
            return None

    # ---- public API -----------------------------------------------------------

    def ensure_agent(self):
        """Make sure a matching-version agent is running; install/update if needed.

        Returns the port it listens on (on the remote's loopback)."""
        with self._lock:
            # fast path: we already know a working agent in this session
            if self._port and self._token:
                info = self.ping(self._port)
                if info and info.get("version") == _local_agent_version():
                    return self._port

            found = self._probe()
            want = _local_agent_version()
            if found:
                port, info = found
                if info.get("version") == want:
                    token = self._load_token()
                    if token:
                        self._port, self._token = port, token
                        return port
                    # agent is running but we cannot authenticate to it: restart
                print(
                    "Remote agent on %s has version %s, expected %s -> updating over SSH"
                    % (self.hostname, info.get("version"), want)
                )
                self._kill()
                time.sleep(0.5)
            try:
                self._install()
                self._start()
            except RemoteError:
                raise
            except Exception as e:
                raise RemoteError(
                    "agent install failed on %s: %r" % (self.hostname, e)
                )
            return self._port

    def request(self, method, path, body=None):
        """Agent request with token handling; auto-recovers from 401."""
        self.ensure_agent()
        for attempt in range(3):
            status, data = self._http(
                method, path, self._port, body=body, token=self._token
            )
            if status != 401:
                return status, data
            # token mismatch: reread the remote token file, else restart agent
            token = self._load_token()
            if attempt == 0 and token and token != self._token:
                self._token = token
                continue
            self._kill()
            time.sleep(0.5)
            self._install()
            self._start()
        raise RemoteError("agent on %s keeps rejecting the token" % self.hostname)

    def scan(self, remote_root, on_entries, progress_cb=None):
        """Scan remote_root on the remote host.

        `on_entries` is called with batches of entries as the remote scan
        progresses (progress sync over the agent port); each entry is
        {"t": "d"|"f", "p": remote_path, ...tags...}. `progress_cb` receives a
        short human-readable status message. Raises RemoteError on failure."""
        scan_id = uuid.uuid4().hex
        status, data = self.request("POST", "/scan", {"id": scan_id, "root": remote_root})
        if status != 200 or not (data or {}).get("ok"):
            raise RemoteError("failed to start remote scan: %s" % (data,))

        cursor = 0
        try:
            while True:
                query = urlencode({"id": scan_id, "cursor": cursor})
                status, data = self.request("GET", "/progress?" + query)
                if status != 200 or not (data or {}).get("ok"):
                    raise RemoteError("remote scan progress failed: %s" % (data,))
                data = data or {}

                entries = data.get("entries") or []
                if entries:
                    on_entries(entries)

                cursor = data.get("cursor", cursor)
                counts = data.get("counts") or {}
                if progress_cb:
                    progress_cb(
                        "%s: %d folders, %d tracks"
                        % (self.hostname, counts.get("dirs", 0), counts.get("tracks", 0))
                    )

                state = data.get("state")
                if state == "done":
                    return
                if state == "error":
                    raise RemoteError("remote scan failed: %s" % data.get("error"))
                time.sleep(POLL_INTERVAL)
        finally:
            try:
                self.request("POST", "/forget", {"id": scan_id})
            except Exception:
                pass


# ---- manager -----------------------------------------------------------------

_clients = {}
_clients_lock = threading.Lock()


def get_client(hostname):
    with _clients_lock:
        if hostname not in _clients:
            _clients[hostname] = RemoteClient(hostname)
        return _clients[hostname]


def ensure_agents_async(roots):
    """Kick off a background agent check/install for every sftp root.

    Called at app startup and when a new SFTP dir is added, so the agent is
    already in place by the time a rescan runs."""
    hosts = []
    for root in roots or []:
        if is_sftp_path(root):
            host = parse_sftp_url(root)[0]
            if host not in hosts:
                hosts.append(host)
    if not hosts:
        return

    def worker():
        for host in hosts:
            try:
                get_client(host).ensure_agent()
                print("FooQt remote agent ready on %s" % host)
            except Exception as e:
                print("Remote agent setup failed for %s: %s" % (host, e))

    threading.Thread(target=worker, daemon=True).start()


# ---- playback streaming ------------------------------------------------------
#
# VLC cannot reuse our paramiko SSH session, so we run a tiny loopback HTTP
# proxy: playback uses http://127.0.0.1:<local>/stream?host=...&path=... and
# each request is relayed to the remote agent's /file endpoint (with Range
# passthrough) over an SSH direct-tcpip channel. This gives instant playback
# start and instant seeking instead of downloading the whole file first.

_stream_proxy = None
_stream_key = None
_stream_lock = threading.Lock()


class _StreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path != "/stream" or (query.get("key") or [""])[0] != _stream_key:
            self.send_error(403)
            return
        host = (query.get("host") or [""])[0]
        remote_path = (query.get("path") or [""])[0]
        if not host or not remote_path:
            self.send_error(400)
            return

        try:
            client = get_client(host)
            client.ensure_agent()
            transport = client._ssh_client().get_transport()
            chan = transport.open_channel(
                "direct-tcpip",
                ("127.0.0.1", client._port),
                ("localhost", 0),
                timeout=10,
            )
        except Exception as e:
            print("Stream setup failed for %s: %s" % (host, e))
            self.send_error(502)
            return

        try:
            chan.settimeout(30)
            lines = [
                "GET /file?path=%s HTTP/1.1" % quote(remote_path),
                "Host: 127.0.0.1",
                "Connection: close",
                "X-Fooqt-Token: %s" % client._token,
            ]
            range_header = self.headers.get("Range")
            if range_header:
                lines.append("Range: %s" % range_header)
            chan.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))

            # read the agent's response headers
            buf = b""
            while b"\r\n\r\n" not in buf:
                data = chan.recv(4096)
                if not data:
                    break
                buf += data
            head, _, body = buf.partition(b"\r\n\r\n")
            head_lines = head.split(b"\r\n")
            status = int(head_lines[0].decode("latin-1").split(" ")[1])
            resp_headers = {}
            for line in head_lines[1:]:
                key, _, value = line.partition(b":")
                resp_headers[
                    key.decode("latin-1").lower().strip()
                ] = value.decode("latin-1").strip()
            length = int(resp_headers.get("content-length") or 0)

            self.send_response(status)
            self.send_header(
                "Content-Type",
                resp_headers.get("content-type", "application/octet-stream"),
            )
            self.send_header("Content-Length", str(length))
            if "content-range" in resp_headers:
                self.send_header("Content-Range", resp_headers["content-range"])
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()

            # relay the body (VLC may hang up early on seek/next)
            sent = 0
            while body and sent < length:
                n = min(len(body), length - sent)
                self.wfile.write(body[:n])
                sent += n
                body = body[n:]
            while sent < length:
                data = chan.recv(STREAM_CHUNK)
                if not data:
                    break
                self.wfile.write(data)
                sent += len(data)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print("Stream relay ended early for %s%s: %s" % (host, remote_path, e))
        finally:
            try:
                chan.close()
            except Exception:
                pass


def _start_stream_proxy():
    global _stream_proxy, _stream_key
    with _stream_lock:
        if _stream_proxy is None:
            _stream_key = secrets.token_hex(8)
            server = ThreadingHTTPServer(("127.0.0.1", 0), _StreamHandler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            _stream_proxy = server
    return _stream_proxy


def stream_url(sftp_url):
    """Return a local http:// URL that VLC can stream a remote file from.

    Raises RemoteError if the remote agent cannot be reached, so the caller
    can fall back to downloading the file."""
    host, remote_path = parse_sftp_url(sftp_url)
    get_client(host).ensure_agent()
    server = _start_stream_proxy()
    return "http://127.0.0.1:%d/stream?key=%s&host=%s&path=%s" % (
        server.server_address[1],
        _stream_key,
        quote(host),
        quote(remote_path),
    )