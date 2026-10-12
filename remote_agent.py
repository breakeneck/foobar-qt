#!/usr/bin/env python3
"""
FooQt remote scan agent.

Self-contained (stdlib-only) helper that the FooQt desktop app deploys onto
SFTP music servers, Zed-remote style:

  * installed to ~/.local/lib/fooqt/remote_agent.py over SFTP
  * listens on 127.0.0.1:45601 (probes up to +9 ports if busy)
  * the desktop client reaches it through an SSH direct-tcpip channel, so the
    port never needs to be exposed on the network
  * scans music dirs locally (fast readdir + tag reading) and streams results
    back incrementally; the client polls /progress and syncs new entries
  * /ping reports VERSION; on mismatch the client re-uploads this file and
    restarts the agent (auto-update over SSH)

Protocol (JSON over HTTP, token in the X-Fooqt-Token header):
  GET  /ping                   -> {"ok", "version", "pid"}      (no token needed)
  POST /scan   {"id", "root", "known"} -> start a scan job
  GET  /progress?id=&cursor=   -> {"state", "cursor", "counts", "entries"}
  GET  /file?path=...          -> stream an audio file (Range supported)
  POST /forget {"id"}          -> drop a finished job

Entry shapes:
  {"t": "d", "p": "/abs/dir"}                              folder
  {"t": "f", "p": "/abs/file", "artist": ..., "title": ...,
                 "album": ..., "dur": duration_secs,
                 "mt": mtime, "sz": size}                  new/changed track
  {"t": "f", "p": "/abs/file", "mt": mtime, "sz": size,
                 "u": 1}                                   unchanged track
                                                          (no tags sent)

"known" maps remote file paths to [mtime, size] fingerprints of files the
client already has; matching files are reported as unchanged so the agent
skips reading their tags.

Tag reading uses eyed3 when it happens to be installed on the remote host;
otherwise it falls back to built-in parsers (ID3v1/ID3v2, Vorbis comments,
FLAC STREAMINFO, MP4 ilst atoms). Unknown fields are simply omitted; the
desktop client applies its own filename-based fallbacks.
"""

VERSION = "1.3.0"

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

try:
    from http.server import ThreadingHTTPServer  # type: ignore[assignment]
except ImportError:  # Python < 3.7
    from http.server import HTTPServer
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):  # type: ignore[no-redef]
        daemon_threads = True


DEFAULT_PORT = 45601
PORT_SPAN = 10
AUDIO_EXTS = {
    ".mp3", ".flac", ".ogg", ".oga", ".m4a", ".m4b", ".mp4",
    ".aac", ".wav", ".wma", ".opus", ".ape", ".wv",
}
MAX_ENTRIES_PER_RESPONSE = 2000
JOB_TTL = 300  # seconds a finished job is kept after the client forgets it
FILE_CHUNK = 1024 * 1024

TOKEN = os.environ.get("FOOQT_REMOTE_TOKEN", "")

LAST_ACTIVITY = time.time()

JOBS = {}
JOBS_LOCK = threading.Lock()


def log(msg):
    print("[fooqt-remote %s] %s" % (VERSION, msg), flush=True)


# ---------------------------------------------------------------------------
# Tag reading (built-in fallbacks, eyed3 preferred when available)
# ---------------------------------------------------------------------------

_eyed3 = None
_eyed3_checked = False


def _get_eyed3():
    global _eyed3, _eyed3_checked
    if not _eyed3_checked:
        _eyed3_checked = True
        try:
            import eyed3 as _e  # type: ignore[import-not-found]

            _eyed3 = _e
        except Exception:
            _eyed3 = None
    return _eyed3


def _read(path, size, offset=0):
    with open(path, "rb") as fh:
        fh.seek(offset)
        return fh.read(size)


def _synchsafe(b):
    n = 0
    for byte in b:
        n = (n << 7) | (byte & 0x7F)
    return n


def _decode_text(data):
    if not data:
        return ""
    enc, body = data[0], data[1:]
    try:
        if enc == 0:
            return body.decode("latin-1", "replace")
        if enc == 1:
            return body.decode("utf-16", "replace")
        if enc == 2:
            return body.decode("utf-16-be", "replace")
        if enc == 3:
            return body.decode("utf-8", "replace")
    except Exception:
        pass
    return body.decode("latin-1", "replace")


def _id3v2(data):
    """Parse an ID3v2 header+body from the start of `data`.

    Returns (tags, total_tag_size)."""
    if len(data) < 10 or data[:3] != b"ID3":
        return {}, 0
    major = data[3]
    flags = data[5]
    size = _synchsafe(data[6:10])
    body = data[10 : 10 + size]
    if major == 3 and flags & 0x80:  # unsynchronisation
        body = body.replace(b"\xff\x00", b"\xff")

    fmap = {
        2: {"TT2": "title", "TP1": "artist", "TAL": "album"},
        3: {"TIT2": "title", "TPE1": "artist", "TALB": "album"},
        4: {"TIT2": "title", "TPE1": "artist", "TALB": "album"},
    }.get(major)
    tags = {}
    if not fmap:
        return tags, 10 + size

    pos = 0
    hdr = 6 if major == 2 else 10
    while pos + hdr <= len(body):
        if major == 2:
            fid = body[pos : pos + 3].decode("latin-1")
            fsz = int.from_bytes(body[pos + 3 : pos + 6], "big")
            pos += 6
        else:
            fid = body[pos : pos + 4].decode("latin-1")
            if fid.strip("\x00") == "":
                break
            fsz = _synchsafe(body[pos + 4 : pos + 8]) if major == 4 \
                else int.from_bytes(body[pos + 4 : pos + 8], "big")
            pos += 10
        if fsz <= 0 or pos + fsz > len(body):
            break
        if fid in fmap:
            val = _decode_text(body[pos : pos + fsz]).strip("\x00").strip()
            if val:
                tags[fmap[fid]] = val
        pos += fsz
    return tags, 10 + size


def _id3v1(path, size):
    if size < 128:
        return {}
    tail = _read(path, 128, size - 128)
    if tail[:3] != b"TAG":
        return {}

    def s(b):
        return b.split(b"\x00")[0].decode("latin-1").strip()

    return {"title": s(tail[3:33]), "artist": s(tail[33:63]), "album": s(tail[63:93])}


# MPEG1 Layer III / MPEG2(.5) Layer III bitrate tables (kbps)
_MP3_BR_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MP3_BR_V2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]


def _mp3_duration(path, size, id3_size):
    """Rough CBR duration estimate from the first MPEG frame header."""
    if size <= id3_size:
        return None
    head = _read(path, min(4096, size - id3_size), id3_size)
    i = 0
    while i + 4 <= len(head):
        if head[i] == 0xFF and (head[i + 1] & 0xE0) == 0xE0:
            b1, b2 = head[i + 1], head[i + 2]
            ver = (b1 >> 3) & 3      # 3=MPEG1, 2=MPEG2, 0=MPEG2.5
            layer = (b1 >> 1) & 3    # 1=Layer III
            br_i = (b2 >> 4) & 0xF
            sr_i = (b2 >> 2) & 3
            if layer == 1 and ver in (3, 2, 0) and 0 < br_i < 15 and sr_i < 3:
                if ver == 3:
                    br = _MP3_BR_V1[br_i]
                else:
                    br = _MP3_BR_V2[br_i]
                if br:
                    return round((size - id3_size - i) * 8.0 / (br * 1000.0))
        i += 1
    return None


def _vorbis_comments(block):
    tags = {}
    pos = 0
    try:
        vlen = int.from_bytes(block[pos:pos + 4], "little")
        pos += 4 + vlen
        count = int.from_bytes(block[pos:pos + 4], "little")
        pos += 4
        for _ in range(count):
            clen = int.from_bytes(block[pos:pos + 4], "little")
            pos += 4
            comment = block[pos:pos + clen]
            pos += clen
            key, _, value = comment.partition(b"=")
            key = key.decode("utf-8", "replace").lower()
            if key in ("artist", "title", "album"):
                tags[key] = value.decode("utf-8", "replace")
    except Exception:
        pass
    return tags


def _flac(path, size):
    data = _read(path, min(size, 64 * 1024))
    if data[:4] != b"fLaC":
        return {}
    tags = {}
    pos = 4
    while pos + 4 <= len(data):
        btype = data[pos] & 0x7F
        is_last = data[pos] & 0x80
        blen = int.from_bytes(data[pos + 1 : pos + 4], "big")
        pos += 4
        block = data[pos : pos + blen]
        if btype == 0 and len(block) >= 18:  # STREAMINFO
            bits = int.from_bytes(block[10:18], "big")
            sr = bits >> 44
            total = bits & ((1 << 36) - 1)
            if sr and total:
                tags["duration"] = round(total / float(sr))
        elif btype == 4:  # VORBIS_COMMENT
            tags.update(_vorbis_comments(block))
        if is_last:
            break
        pos += blen
    return tags


def _ogg_packets(data, want=2):
    """Reassemble the first `want` packets from the start of an Ogg stream."""
    packets = []
    buf = bytearray()
    pos = 0
    n = len(data)
    while pos + 27 <= n and len(packets) < want:
        if data[pos:pos + 4] != b"OggS":
            pos += 1
            continue
        seg_count = data[pos + 26]
        segs = data[pos + 27 : pos + 27 + seg_count]
        if len(segs) < seg_count:
            break
        pos += 27 + seg_count
        for v in segs:
            if pos + v > n:
                break
            buf += data[pos : pos + v]
            pos += v
            if v < 255:
                packets.append(bytes(buf))
                buf = bytearray()
                if len(packets) >= want:
                    break
    return packets


def _ogg(path, size):
    tags = {}
    head = _read(path, min(size, 64 * 1024))
    packets = _ogg_packets(head, 2)
    sr = None
    if packets and packets[0][:7] == b"\x01vorbis" and len(packets[0]) >= 15:
        sr = int.from_bytes(packets[0][11:15], "little")
    if len(packets) > 1 and packets[1][:7] == b"\x03vorbis":
        tags.update(_vorbis_comments(packets[1][7:]))
    if sr:
        tail = _read(path, min(32 * 1024, size), max(0, size - 32 * 1024))
        idx = tail.rfind(b"OggS")
        if idx != -1 and idx + 14 <= len(tail):
            granule = int.from_bytes(tail[idx + 6 : idx + 14], "little")
            if 0 < granule < (1 << 63) - 1:
                tags["duration"] = round(granule / float(sr))
    return tags


_MP4_TEXT_ATOMS = {b"\xa9nam": "title", b"\xa9ART": "artist", b"\xa9alb": "album"}
_MP4_CONTAINERS = {b"moov", b"udta", b"trak", b"mdia", b"minf", b"stbl", b"ilst"}


def _mp4(path):
    tags = {}
    duration = [0]
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        def walk(start, end, depth):
            if depth > 6:
                return
            pos = start
            while pos + 8 <= end:
                fh.seek(pos)
                hdr = fh.read(8)
                if len(hdr) < 8:
                    return
                sz = int.from_bytes(hdr[:4], "big")
                typ = hdr[4:8]
                body_off = 8
                if sz == 1:
                    ext = fh.read(8)
                    if len(ext) < 8:
                        return
                    sz = int.from_bytes(ext, "big")
                    body_off = 16
                elif sz == 0:
                    sz = end - pos
                if sz < body_off:
                    return
                inner_start = pos + body_off
                inner_end = pos + sz
                if typ in _MP4_CONTAINERS:
                    walk(inner_start, inner_end, depth + 1)
                elif typ == b"meta":
                    walk(inner_start + 4, inner_end, depth + 1)
                elif typ == b"mvhd":
                    body = fh.read(min(sz - body_off, 40))
                    if len(body) >= 20:
                        if body[0] == 1 and len(body) >= 32:
                            ts = int.from_bytes(body[20:24], "big")
                            du = int.from_bytes(body[24:32], "big")
                        else:
                            ts = int.from_bytes(body[12:16], "big")
                            du = int.from_bytes(body[16:20], "big")
                        if ts:
                            duration[0] = round(du / float(ts))
                elif typ in _MP4_TEXT_ATOMS:
                    body = fh.read(min(sz - body_off, 4096))
                    i = 0
                    while i + 16 <= len(body):
                        dsz = int.from_bytes(body[i:i + 4], "big")
                        dtyp = body[i + 4 : i + 8]
                        if dsz < 8:
                            break
                        if dtyp == b"data":
                            tags[_MP4_TEXT_ATOMS[typ]] = \
                                body[i + 16 : i + dsz].decode("utf-8", "replace")
                            break
                        i += dsz
                pos += sz

        walk(0, size, 0)
    if duration[0]:
        tags["duration"] = duration[0]
    return tags


def _tags_eyed3(path):
    e3 = _get_eyed3()
    if e3 is None:
        return None
    try:
        f = e3.load(path)
        if f is None:
            return None
        tags = {}
        try:
            if f.info and f.info.time_secs:
                tags["duration"] = int(f.info.time_secs)
        except Exception:
            pass
        try:
            if f.tag:
                if f.tag.artist:
                    tags["artist"] = f.tag.artist
                if f.tag.title:
                    tags["title"] = f.tag.title
                if f.tag.album:
                    tags["album"] = f.tag.album
        except Exception:
            pass
        return tags
    except Exception:
        return None


def read_tags(path):
    """Best-effort tags for one audio file. Missing keys are omitted."""
    tags = _tags_eyed3(path)
    if tags is not None:
        return tags
    ext = os.path.splitext(path)[1].lower()
    try:
        size = os.path.getsize(path)
        if ext == ".mp3":
            tags = {}
            head = _read(path, min(size, 64 * 1024))
            id3_size = 0
            if head[:3] == b"ID3":
                t, id3_size = _id3v2(head)
                tags.update(t)
            v1 = _id3v1(path, size)
            for key in ("artist", "title", "album"):
                if not tags.get(key) and v1.get(key):
                    tags[key] = v1[key]
            dur = _mp3_duration(path, size, id3_size)
            if dur:
                tags["duration"] = dur
            return tags
        if ext == ".flac":
            return _flac(path, size)
        if ext in (".ogg", ".oga"):
            return _ogg(path, size)
        if ext in (".m4a", ".m4b", ".mp4"):
            return _mp4(path)
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Scan jobs
# ---------------------------------------------------------------------------

class ScanJob:
    def __init__(self, scan_id, root, known=None):
        self.id = scan_id
        self.root = root
        self.known = known or {}
        self.entries = []
        self.counts = {"dirs": 0, "tracks": 0}
        self.lock = threading.Lock()
        self.state = "running"
        self.error = None
        self.finished_at = None

    def add(self, entry):
        with self.lock:
            self.entries.append(entry)
            if entry["t"] == "d":
                self.counts["dirs"] += 1
            else:
                self.counts["tracks"] += 1

    def run(self):
        try:
            if not os.path.isdir(self.root):
                raise ValueError("root is not a directory: %s" % self.root)
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames.sort()
                if dirpath != self.root:
                    # the client inserts the root itself; only report children
                    self.add({"t": "d", "p": dirpath})
                for fn in sorted(filenames):
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in AUDIO_EXTS:
                        continue
                    full = os.path.join(dirpath, fn)
                    try:
                        st = os.stat(full)
                        mt, sz = int(st.st_mtime), st.st_size
                    except OSError:
                        continue
                    if self.known.get(full) == [mt, sz]:
                        # unchanged since the client's last scan: report the
                        # fingerprint only, skip reading the tags
                        self.add({"t": "f", "p": full, "mt": mt, "sz": sz, "u": 1})
                        continue
                    tags = read_tags(full)
                    self.add({
                        "t": "f",
                        "p": full,
                        "artist": tags.get("artist"),
                        "title": tags.get("title"),
                        "album": tags.get("album"),
                        "dur": tags.get("duration"),
                        "mt": mt,
                        "sz": sz,
                    })
        except Exception as e:
            self.error = str(e)
            self.state = "error"
        if self.state == "running":
            self.state = "done"
        self.finished_at = time.time()


def _cleanup_jobs():
    now = time.time()
    with JOBS_LOCK:
        stale = [
            jid for jid, job in JOBS.items()
            if job.finished_at and now - job.finished_at > JOB_TTL
        ]
        for jid in stale:
            del JOBS[jid]


def _parse_range(header, size):
    """Parse a single-range HTTP Range header -> (start, end) inclusive."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    start_s, _, end_s = spec.partition("-")
    try:
        if start_s == "":  # suffix range: last N bytes
            length = int(end_s)
            if length <= 0:
                return None
            start, end = max(0, size - length), size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                return None
    except ValueError:
        return None
    return start, end


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "FooQtRemote/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # keep the remote log quiet
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        return not TOKEN or self.headers.get("X-Fooqt-Token") == TOKEN

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        global LAST_ACTIVITY
        LAST_ACTIVITY = time.time()
        url = urlparse(self.path)
        query = parse_qs(url.query)

        if url.path == "/ping":
            return self._send(200, {
                "ok": True,
                "version": VERSION,
                "pid": os.getpid(),
            })

        if not self._authorized():
            return self._send(401, {"ok": False, "error": "bad token"})

        if url.path == "/progress":
            _cleanup_jobs()
            scan_id = (query.get("id") or [""])[0]
            try:
                cursor = int((query.get("cursor") or ["0"])[0])
            except ValueError:
                cursor = 0
            with JOBS_LOCK:
                job = JOBS.get(scan_id)
            if job is None:
                return self._send(404, {"ok": False, "error": "no such scan"})
            with job.lock:
                chunk = job.entries[cursor : cursor + MAX_ENTRIES_PER_RESPONSE]
                new_cursor = cursor + len(chunk)
                counts = dict(job.counts)
                state = job.state
                error = job.error
            return self._send(200, {
                "ok": True,
                "state": state,
                "cursor": new_cursor,
                "counts": counts,
                "error": error,
                "entries": chunk,
            })

        if url.path == "/file":
            return self._serve_file(query, include_body=True)

        return self._send(404, {"ok": False, "error": "not found"})

    def do_HEAD(self):
        global LAST_ACTIVITY
        LAST_ACTIVITY = time.time()
        url = urlparse(self.path)
        if not self._authorized():
            self.send_error(401)
            return
        if url.path == "/file":
            return self._serve_file(parse_qs(url.query), include_body=False)
        self.send_error(404)

    def _serve_file(self, query, include_body=True):
        """Stream one audio file with Range support (instant playback start
        and seeking for the desktop client's local proxy)."""
        path = (query.get("path") or [""])[0]
        ext = os.path.splitext(path)[1].lower()
        # the token grants access to audio files only, not arbitrary reads
        if ext not in AUDIO_EXTS or not os.path.isfile(path):
            return self._send(404, {"ok": False, "error": "no such audio file"})
        try:
            size = os.path.getsize(path)
        except OSError as e:
            return self._send(404, {"ok": False, "error": str(e)})

        status = 200
        start, end = 0, size - 1
        rng = _parse_range(self.headers.get("Range"), size)
        if rng:
            start, end = rng
            status = 206
        length = max(0, end - start + 1)

        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Connection", "close")
        self.end_headers()
        if not include_body:
            return

        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(FILE_CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client hung up (VLC seek / next track) - normal

    def do_POST(self):
        global LAST_ACTIVITY
        LAST_ACTIVITY = time.time()
        url = urlparse(self.path)
        if not self._authorized():
            return self._send(401, {"ok": False, "error": "bad token"})
        body = self._read_body()

        if url.path == "/scan":
            scan_id = body.get("id")
            root = body.get("root")
            known = body.get("known") or {}
            if not scan_id or not root:
                return self._send(400, {"ok": False, "error": "id and root required"})
            with JOBS_LOCK:
                existing = JOBS.get(scan_id)
                if existing is None:
                    job = ScanJob(scan_id, root, known)
                    JOBS[scan_id] = job
                    threading.Thread(target=job.run, daemon=True).start()
                    return self._send(200, {"ok": True, "started": True})
            return self._send(200, {"ok": True, "started": False})

        if url.path == "/forget":
            scan_id = body.get("id")
            with JOBS_LOCK:
                job = JOBS.pop(scan_id, None)
            if job is not None:
                job.finished_at = None  # free memory even if still running
            return self._send(200, {"ok": True})

        return self._send(404, {"ok": False, "error": "not found"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _watchdog(idle_timeout):
    while True:
        time.sleep(30)
        if time.time() - LAST_ACTIVITY > idle_timeout:
            log("idle for %ds, exiting" % idle_timeout)
            os._exit(0)


def main():
    ap = argparse.ArgumentParser(description="FooQt remote scan agent")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--state-dir", default=os.path.expanduser("~/.local/lib/fooqt"))
    ap.add_argument("--idle-timeout", type=int, default=7200,
                    help="exit after this many seconds without client activity")
    args = ap.parse_args()

    try:
        os.makedirs(args.state_dir, exist_ok=True)
    except Exception:
        pass

    server = None
    bound_port = None
    for port in range(args.port, args.port + PORT_SPAN):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            bound_port = port
            break
        except OSError:
            continue
    if server is None:
        log("no free port in %d..%d" % (args.port, args.port + PORT_SPAN - 1))
        sys.exit(2)

    server.daemon_threads = True
    try:
        with open(os.path.join(args.state_dir, ".port"), "w") as f:
            f.write(str(bound_port))
    except Exception:
        pass
    if TOKEN:
        try:
            _write_private(os.path.join(args.state_dir, ".token"), TOKEN)
        except Exception:
            pass

    threading.Thread(
        target=_watchdog, args=(args.idle_timeout,), daemon=True
    ).start()
    log("listening on 127.0.0.1:%d (pid %d)" % (bound_port, os.getpid()))
    server.serve_forever()


if __name__ == "__main__":
    main()