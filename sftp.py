"""
SFTP connection manager that uses local SSH config (~/.ssh/config) for authentication.
Connections are keyed by hostname, so a single connection is reused.
"""

import os

import paramiko


class SFTPConnection:
    """Manages a single SFTP connection."""

    def __init__(self, hostname: str, username: str = "", port: int = 22):
        self.hostname = hostname
        self.username = username
        self.port = port
        self.client = None
        self.sftp = None

    def connect(self):
        # Check existing connection via the SSH client's transport (not sftp.transport)
        if self.sftp and self.client and self.client.get_transport().is_active():
            return self.sftp

        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Load SSH config so that ~/.ssh/config host aliases / keys / ports work
        ssh_config = paramiko.SSHConfig()
        ssh_path = os.path.expanduser("~/.ssh/config")
        if os.path.exists(ssh_path):
            with open(ssh_path) as f:
                ssh_config.parse(f)

        host_config = ssh_config.lookup(self.hostname)
        kwargs = {}
        if host_config.get("hostname"):
            kwargs["hostname"] = host_config["hostname"]
        else:
            kwargs["hostname"] = self.hostname

        if host_config.get("user"):
            kwargs["username"] = host_config["user"]
        elif self.username:
            kwargs["username"] = self.username

        if host_config.get("port"):
            kwargs["port"] = int(host_config["port"])
        else:
            kwargs["port"] = self.port

        # Look for identity files
        if host_config.get("identityfile"):
            identity_files = host_config["identityfile"]
            if isinstance(identity_files, str):
                identity_files = [f.strip() for f in identity_files.split()]
            kwargs["key_filename"] = [os.path.expanduser(f) for f in identity_files]

        self.client.connect(**kwargs)
        self.sftp = self.client.open_sftp()
        return self.sftp

    def ensure_connected(self):
        """Connect if not already connected."""
        try:
            return self.connect()
        except Exception as e:
            print("Failed to connect to SFTP host '%s': %s" % (self.hostname, e))
            raise

    def close(self):
        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.sftp = None
        self.client = None


class SFTPManager:
    """Pool of SFTP connections, keyed by hostname."""

    def __init__(self):
        self._connections = {}

    def get_connection(self, hostname, username="", port=22):
        if hostname not in self._connections:
            self._connections[hostname] = SFTPConnection(hostname, username, port)
        return self._connections[hostname]

    def close_all(self):
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()


# Global singleton
_manager = SFTPManager()


def get_sftp_manager():
    return _manager
