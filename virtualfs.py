"""
Virtual filesystem abstraction layer.
Provides a uniform interface for both local and SFTP paths.
SFTP paths use the format: sftp://hostname/path/to/file
"""

import os
import stat
import tempfile

from sftp import get_sftp_manager


def is_sftp_path(path) -> bool:
    return path.startswith("sftp://")


def parse_sftp_url(url: str) -> tuple[str, str]:
    """Parse sftp://hostname/path into (hostname, remote_path)."""
    after_scheme = url[len("sftp://") :]
    first_slash = after_scheme.find("/")
    if first_slash == -1:
        return after_scheme, "/"
    hostname = after_scheme[:first_slash]
    remote_path = after_scheme[first_slash:]
    return hostname, remote_path


def _get_sftp_and_path(path):
    hostname, remote_path = parse_sftp_url(path)
    sftp_manager = get_sftp_manager()
    conn = sftp_manager.get_connection(hostname)
    sftp = conn.ensure_connected()
    return sftp, remote_path


# ---- Filesystem operations ----


def listdir(path: str) -> list:
    if is_sftp_path(path):
        sftp, remote_path = _get_sftp_and_path(path)
        try:
            attrs = sftp.listdir_attr(remote_path)
        except OSError as e:
            print("SFTP listdir failed for %s: %s" % (path, e))
            return []
        names = []
        for attr in attrs:
            if attr.filename in (".", ".."):
                continue
            names.append(attr.filename)
        return names
    return os.listdir(path)


def isdir(path: str) -> bool:
    if is_sftp_path(path):
        sftp, remote_path = _get_sftp_and_path(path)
        try:
            attr = sftp.stat(remote_path)
            mode = attr.st_mode
            if mode is None:
                return False
            return stat.S_ISDIR(mode)
        except OSError:
            return False
    return os.path.isdir(path)


def isfile(path: str) -> bool:
    if is_sftp_path(path):
        sftp, remote_path = _get_sftp_and_path(path)
        try:
            attr = sftp.stat(remote_path)
            mode = attr.st_mode
            if mode is None:
                return False
            return stat.S_ISREG(mode)
        except OSError:
            return False
    return os.path.isfile(path)


def basename(path: str) -> str:
    if is_sftp_path(path):
        _, remote_path = parse_sftp_url(path)
        return os.path.basename(remote_path)
    return os.path.basename(path)


def dirname(path: str) -> str:
    if is_sftp_path(path):
        hostname, remote_path = parse_sftp_url(path)
        parent = os.path.dirname(remote_path)
        return "sftp://{}{}".format(hostname, parent)
    return os.path.dirname(path)


def join(*paths: str) -> str:
    """Join path components. Detects if the base path is sftp://."""
    if is_sftp_path(paths[0]):
        hostname, base = parse_sftp_url(paths[0])
        combined = os.path.join(base, *paths[1:])
        return "sftp://{}{}".format(hostname, combined)
    return os.path.join(*paths)


def exists(path: str) -> bool:
    if is_sftp_path(path):
        sftp, remote_path = _get_sftp_and_path(path)
        try:
            sftp.stat(remote_path)
            return True
        except OSError:
            return False
    return os.path.exists(path)


def getsize(path: str) -> int:
    if is_sftp_path(path):
        sftp, remote_path = _get_sftp_and_path(path)
        size = sftp.stat(remote_path).st_size
        return size if size else 0
    return os.path.getsize(path)


def open_file_to_temp(path: str) -> tuple[str, bool]:
    """
    For SFTP files, download to a temp file and return its local path.
    For local files, just return the path as-is.
    The caller is responsible for cleaning up the temp file if is_temp is True.
    """
    if is_sftp_path(path):
        sftp, remote_path = _get_sftp_and_path(path)
        temp_fd, temp_path = tempfile.mkstemp(suffix=basename(remote_path) or ".tmp")
        try:
            remote_file = sftp.file(remote_path, "rb")
            os.write(temp_fd, remote_file.read())
            remote_file.close()
        finally:
            os.close(temp_fd)
        return temp_path, True
    return path, False


def get_tree_path(root, path, root_label):
    """
    Compute the tree path for a folder under a given root.

    For the root folder itself, returns root_label.
    For sub-folders, returns root_label/relative/path.

    Examples:
        root='/home/yuri/Music', path='/home/yuri/Music' -> 'Music'
        root='/home/yuri/Music', path='/home/yuri/Music/Artist' -> 'Music/Artist'
        root='sftp://ha/home/ha/hdd/storage/music', path=root -> 'ha://music'
        root='sftp://ha/...', path='sftp://ha/.../artist/album' -> 'ha://music/artist/album'
    """
    if path == root:
        return root_label
    if path.startswith(root):
        rel = path[len(root) :].lstrip("/")
        return root_label + "/" + rel
    return basename(path)


def get_root_label(root):
    """
    Get the display name for a library root directory.

    For SFTP: 'hostname://lastdir' (e.g. 'ha://music')
    For local: just the dirname (e.g. 'Music')
    """
    if is_sftp_path(root):
        host, remote_path = parse_sftp_url(root)
        last_part = remote_path.rstrip("/").rsplit("/", 1)[-1]
        return host + "://" + last_part
    return os.path.basename(root)


def test_connection(sftp_url: str) -> tuple[bool, str]:
    """Test if an SFTP URL is reachable and the path exists."""
    if not is_sftp_path(sftp_url):
        return True, "OK"
    try:
        sftp, remote_path = _get_sftp_and_path(sftp_url)
        attrs = sftp.listdir_attr(remote_path)
        return True, "OK (%d entries)" % len(attrs)
    except OSError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)
