import os
from pathlib import Path

import eyed3

import database
import remote
from virtualfs import (
    basename,
    dirname,
    get_root_label,
    get_tree_path,
    is_sftp_path,
    join,
    listdir_stat,
    open_file_to_temp,
    parse_sftp_url,
)


class Library:
    FOLDER_TABLE_NAME = "folder"
    TRACK_TABLE_NAME = "track"
    STATS_TABLE_NAME = "track_stat"

    root_dir: str = ""
    selected_dir = ""
    selected_dir_row = -1
    library_dirs: list = []

    def __init__(self, dirs=None):
        if isinstance(dirs, list) and dirs and isinstance(dirs[0], str):
            self.library_dirs = [d for d in dirs if d]
            self.root_dir = self.library_dirs[0] if self.library_dirs else ""
            self.selected_dir = ""
            self.selected_dir_row = -1
        else:
            self.updateDirs(dirs)
        isDbExists = database.connect()
        if not isDbExists:
            Track().create_table()
            Folder().create_table()
        # needed on both fresh and pre-stats databases
        self.ensureStatsTable()
        self.scanner = Scanner(self)
        # note: database.connect() returns a falsy value in both branches,
        # so don't gate on isDbExists; migration is a no-op on a fresh DB
        self.migrateGroupNames()

    def ensureStatsTable(self):
        """Per-file fingerprints (mtime+size) used to skip unchanged files
        on rescan. Kept in its own table so the track table and the table
        view (Track.colCount) stay untouched."""
        database.db.execute(
            "CREATE TABLE IF NOT EXISTS %s "
            "(full_path text PRIMARY KEY, mtime real, size integer)"
            % Library.STATS_TABLE_NAME
        )

    def migrateGroupNames(self):
        """Recompute stored group names with the current get_short_dir_name
        logic. They are a pure function of the stored paths plus the current
        root dirs, so a format change does not require a full rescan."""
        try:
            scanner = self.scanner
            for table, path_col, name_col in (
                (Library.TRACK_TABLE_NAME, "dir_name", "base_dir_name"),
                (Library.FOLDER_TABLE_NAME, "path", "short_dir_name"),
            ):
                database.db.execute(
                    f"SELECT DISTINCT {path_col} FROM {table}"
                )
                paths = [row[0] for row in database.db.fetchall()]
                for path in paths:
                    root = scanner.get_root_for_path(path)
                    if not root:
                        continue
                    new_name = scanner.get_short_dir_name(path, root)
                    database.db.execute(
                        f"UPDATE {table} SET {name_col} = ? WHERE {path_col} = ?",
                        (new_name, path),
                    )
        except Exception as e:
            print("group name migration failed: %r" % e)

    def updateDirs(self, dirs):
        self.root_dir, self.selected_dir, self.selected_dir_row = dirs

    def addDir(self, directory):
        if directory and directory not in self.library_dirs:
            self.library_dirs.append(directory)
            self.root_dir = self.library_dirs[0]

    def removeDir(self, directory):
        if directory in self.library_dirs:
            self.library_dirs.remove(directory)
            if directory == self.root_dir:
                self.root_dir = self.library_dirs[0] if self.library_dirs else ""

    def purgeDir(self, directory):
        """Delete the cached rows (tracks, folders, stats) of a library root.

        Uses an escaped LIKE prefix so a sibling like 'Music2' is not caught
        by a 'Music' removal ('%' and '_' in the path are escaped)."""
        like = (
            directory.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "/%"
        )
        for table, path_col in (
            (Library.TRACK_TABLE_NAME, "dir_name"),
            (Library.FOLDER_TABLE_NAME, "path"),
            (Library.STATS_TABLE_NAME, "full_path"),
        ):
            database.db.execute(
                "DELETE FROM %s WHERE %s = ? OR %s LIKE ? ESCAPE '\\'"
                % (table, path_col, path_col),
                [directory, like],
            )

    def getAllRootDirs(self):
        if self.library_dirs:
            return self.library_dirs
        return [self.root_dir] if self.root_dir else []

    def rescan(self, paths=None, progress_cb=None):
        """Incrementally rescan the given subtrees (all roots when empty).

        Unchanged files (same mtime+size) are not re-read and their DB rows
        are left untouched; only new/changed files are scanned and rows for
        vanished files/folders are deleted."""
        roots = self.getAllRootDirs()
        targets = [p for p in (paths or roots) if p] or roots
        self.scanner.rescan(targets, progress_cb)


class Folder(database.Model):
    def __init__(self):
        self.id = 0
        self.path = ""
        self.basename = ""
        self.short_dir_name = ""
        self.parent_dir = ""
        self.is_expanded = 0

    @property
    def tableName(self):
        return Library.FOLDER_TABLE_NAME

    @property
    def indexedAttrs(self):
        return ["path"]

    def find(self, path):
        database.db.execute(f'SELECT * FROM {self.tableName} WHERE path = "{path}"')
        return Folder().load(database.db.fetchone())

    def getAll(self):
        database.db.execute(f"SELECT * FROM {self.tableName} ORDER BY path")
        return map(lambda row: Folder().load(row), database.db.fetchall())

    def getRelPath(self, library):
        """
        Get the tree path for display. Returns a string like:
          Local: 'Music/Artist/Album'
          SFTP: 'ha://music/Artist/Album'
        The tree builder splits this by '/' to create nested nodes.
        The root node label will contain '://' for SFTP roots.
        """
        for root in library.getAllRootDirs():
            if self.path.startswith(root):
                root_label = get_root_label(root)
                return get_tree_path(root, self.path, root_label)
        return self.path


class Track(database.Model):
    def __init__(self):
        self.id = 0
        self.artist = ""
        self.title = ""
        self.album = ""
        self.year = 0
        self.track_num = 0
        self.basename = ""
        self.full_path = ""
        self.dir_name = ""
        self.base_dir_name = ""
        self.duration = 0
        self.skipped = 0

    @staticmethod
    def colCount():
        return 12

    @property
    def indexedAttrs(self):
        return ["artist", "title", "dir_name"]

    @property
    def tableName(self):
        return Library.TRACK_TABLE_NAME

    def getTitle(self):
        return self.artist + " - " + self.title

    def getFolder(self):
        return Folder().find(self.dir_name)

    def getAttrValues(self):
        return tuple(self.__dict__.values())

    def getAttrLabels(self):
        return [*self.__dict__.keys()]

    def getAllByPath(self, path, query=""):
        conditions = []
        if query:
            conditions.append(f'(title LIKE "%{query}%" OR artist LIKE "%{query}%")')
        if path:
            conditions.append(f'(dir_name LIKE "{path}%")')

        database.db.execute(
            f"SELECT * FROM {self.tableName}"
            + (" WHERE " + " AND ".join(conditions) if conditions else "")
            + " ORDER BY full_path"
        )
        return map(lambda row: Track().load(row), database.db.fetchall())

    @staticmethod
    def indexByPath(tracks):
        indexed = {}
        for track in tracks:
            indexed[track.full_path] = track
        return indexed

    @staticmethod
    def getPlaylist(library, root_dir=None, query=""):
        if root_dir is None:
            root_dir = (
                library.selected_dir if library.selected_dir else library.root_dir
            )
        path = library.selected_dir if library.selected_dir else root_dir

        playlist = []
        tracks = []

        current_dir = ""
        for track in Track().getAllByPath(path, query):
            if track.base_dir_name != current_dir:
                current_dir = track.base_dir_name

                dir_row = [""] * (Track.colCount())
                dir_row[0] = current_dir
                playlist.append(tuple(dir_row))
                tracks.append(current_dir)

            playlist.append(track.getAttrValues())
            tracks.append(track)

        return tracks, playlist


class Scanner:
    library: Library
    tracks = {}

    def __init__(self, library):
        self.library = library

    def rescan(self, targets, progress_cb=None):
        self.tracks = {}
        try:
            for target in targets:
                self.rescan_tree(target, progress_cb)
        finally:
            self.tracks = []

    @staticmethod
    def _under(parent, path):
        """True when path is parent or lives inside it (exact prefix, unlike
        the LIKE prefix used elsewhere)."""
        return path == parent or path.startswith(parent.rstrip("/") + "/")

    def rescan_tree(self, target, progress_cb=None):
        # Any sftp target (root or subfolder) is scanned by the remote agent
        # on the remote machine itself; fall back to the slow SFTP walk when
        # the agent is unavailable.
        if is_sftp_path(target):
            if self.rescan_remote(target, progress_cb):
                return
        self.rescan_walk(target, progress_cb)

    def _existing_tracks_under(self, target):
        existing = {}
        for t in Track().getAllByPath(target, ""):
            if self._under(target, t.dir_name):
                existing[t.full_path] = t
        return existing

    def _existing_folders_under(self, target):
        database.db.execute(f"SELECT path FROM {Library.FOLDER_TABLE_NAME}")
        return {
            row[0] for row in database.db.fetchall() if self._under(target, row[0])
        }

    def _load_stats_under(self, target):
        database.db.execute(
            f"SELECT full_path, mtime, size FROM {Library.STATS_TABLE_NAME}"
        )
        return {
            row[0]: (row[1], row[2])
            for row in database.db.fetchall()
            if self._under(target, row[0])
        }

    def _save_stat(self, full_path, stat):
        database.db.execute(
            f"INSERT OR REPLACE INTO {Library.STATS_TABLE_NAME}"
            " (full_path, mtime, size) VALUES (?, ?, ?)",
            [full_path, stat[0], stat[1]],
        )

    def _delete_track_row(self, full_path):
        database.db.execute(
            f"DELETE FROM {Library.TRACK_TABLE_NAME} WHERE full_path = ?",
            [full_path],
        )
        database.db.execute(
            f"DELETE FROM {Library.STATS_TABLE_NAME} WHERE full_path = ?",
            [full_path],
        )

    def _cleanup_vanished(
        self, target, existing, seen_files, existing_folders, seen_dirs
    ):
        for path in existing:
            if path not in seen_files:
                self._delete_track_row(path)
        for path in existing_folders - seen_dirs:
            database.db.execute(
                f"DELETE FROM {Library.FOLDER_TABLE_NAME} WHERE path = ?", [path]
            )

    def rescan_walk(self, target, progress_cb=None):
        """Local subtree scan (also the SFTP fallback). Uses listdir_stat so
        file fingerprints come for free with the directory listing."""
        existing = self._existing_tracks_under(target)
        existing_folders = self._existing_folders_under(target)
        known_stats = self._load_stats_under(target)

        seen_files = set()
        seen_dirs = set()

        def on_dir(path):
            seen_dirs.add(path)
            if path not in existing_folders:
                self.insert_dir(path)

        def on_file(path, mtime, size):
            seen_files.add(path)
            old = existing.get(path)
            if old is not None:
                known = known_stats.get(path)
                if known is None or (known[0], known[1]) == (mtime, size):
                    # Unchanged. "stat unknown yet" covers rows written
                    # before fingerprint tracking existed: trust them once
                    # and record the current stat for the next scan.
                    self._save_stat(path, (mtime, size))
                    return
                self._delete_track_row(path)
            self.insert_track(path, stat=(mtime, size), keep_skipped=old)

        on_dir(target)
        try:
            self._walk(target, on_dir, on_file)
        except OSError as e:
            # A partial walk must not delete anything: bail out and keep the
            # rows we did not manage to see.
            print("Scan of %s failed: %s" % (target, e))
            return

        self._cleanup_vanished(
            target, existing, seen_files, existing_folders, seen_dirs
        )

    def _walk(self, dir_name, on_dir, on_file):
        for name, is_dir, mtime, size in listdir_stat(dir_name):
            full_path = join(dir_name, name)
            if is_dir:
                on_dir(full_path)
                self._walk(full_path, on_dir, on_file)
            else:
                on_file(full_path, mtime, size)

    def rescan_remote(self, target, progress_cb=None):
        """Scan an sftp subtree through the remote agent. Returns True on
        success, False if the agent could not be used (caller falls back)."""
        host, remote_target = parse_sftp_url(target)
        try:
            client = remote.get_client(host)
            client.ensure_agent()
        except Exception as e:
            print(
                "Remote agent unavailable for %s (%s); falling back to SFTP walk"
                % (host, e)
            )
            return False

        existing = self._existing_tracks_under(target)
        existing_folders = self._existing_folders_under(target)
        known_stats = self._load_stats_under(target)

        # Fingerprint map for the agent: files it recognises as unchanged are
        # reported without tags, so the remote host skips reading them.
        known = {}
        for path, (mtime, size) in known_stats.items():
            known[parse_sftp_url(path)[1]] = [int(mtime), int(size)]

        seen_files = set()
        seen_dirs = set()

        def on_entries(entries):
            for entry in entries:
                full_path = "sftp://%s%s" % (host, entry["p"])
                if entry["t"] == "d":
                    seen_dirs.add(full_path)
                    if full_path not in existing_folders:
                        self.insert_dir(full_path)
                    continue

                seen_files.add(full_path)
                old = existing.get(full_path)
                mt, sz = entry.get("mt"), entry.get("sz")
                stat = (float(mt), int(sz)) if mt is not None else None

                if old is not None and entry.get("u"):
                    # Agent confirmed the file is unchanged: keep the row.
                    if stat is not None:
                        self._save_stat(full_path, stat)
                    continue
                if old is not None and stat is None:
                    # Pre-1.2.0 agent without fingerprint support: the
                    # stored row for a known path stays as it is.
                    continue
                if old is not None:
                    self._delete_track_row(full_path)
                self.insert_track(
                    full_path,
                    tags={
                        "duration": entry.get("dur"),
                        "artist": entry.get("artist"),
                        "title": entry.get("title"),
                        "album": entry.get("album"),
                    },
                    stat=stat,
                    keep_skipped=old,
                )

        try:
            client.scan(
                remote_target,
                on_entries,
                progress_cb and (lambda msg: progress_cb(msg)),
                known=known,
            )
        except Exception as e:
            print("Remote scan failed for %s (%s)" % (target, e))
            return False

        # The agent reports children only; the scan target itself is handled
        # here and must count as seen so cleanup does not delete it.
        seen_dirs.add(target)
        if target not in existing_folders:
            self.insert_dir(target)
        self._cleanup_vanished(
            target, existing, seen_files, existing_folders, seen_dirs
        )
        return True

    def get_root_for_path(self, full_path):
        """Find which root dir this path belongs to."""
        for root in self.library.getAllRootDirs():
            if full_path.startswith(root):
                return root
        return ""

    def get_short_dir_name(self, full_path, root_dir):
        """
        Compute display name for track grouping in the table view.
        The path is shown relative to the library root (the target dir),
        e.g. 'Artist/Album'; tracks directly in the target dir group under
        its basename. With several library roots the root label is kept as a
        prefix ('ha://music/Artist') so the groups stay unambiguous.
        """
        if full_path == root_dir:
            rel = ""
        elif full_path.startswith(root_dir):
            rel = full_path[len(root_dir) :].lstrip("/")
        else:
            return basename(full_path)
        if len(self.library.getAllRootDirs()) > 1:
            root_label = get_root_label(root_dir)
            return root_label + ("/" + rel if rel else "")
        return rel if rel else basename(root_dir)

    def insert_dir(self, full_path):
        folder = Folder()
        folder.path = full_path
        folder.basename = basename(full_path)
        root_dir = self.get_root_for_path(full_path)
        folder.short_dir_name = self.get_short_dir_name(full_path, root_dir)
        all_roots = self.library.getAllRootDirs()
        folder.parent_dir = "" if full_path in all_roots else dirname(full_path)
        folder.is_expanded = 0
        folder.insert()

    def _read_local_tags(self, full_path):
        """Read tags locally (downloading SFTP files to a temp file).
        Returns a tags dict, or None if the file is not loadable."""
        try:
            local_path, is_temp = open_file_to_temp(full_path)
            try:
                file = eyed3.load(local_path)
                duration = file.info.time_secs
                if not duration:
                    return None
            finally:
                if is_temp:
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
        except:
            print("Critical error on loading tag for", full_path)
            return None

        tags = {"duration": duration}
        try:
            tags["artist"] = file.tag.artist
            tags["title"] = file.tag.title
            tags["album"] = file.tag.album
        except:
            print("Tag error for file", full_path)
        return tags

    def insert_track(self, full_path, tags=None, stat=None, keep_skipped=None):
        """Insert a track. If tags (duration/artist/title/album) were already
        read by the remote agent they are reused instead of fetching the
        file over SFTP. keep_skipped carries the user's skip flag over from
        the previous row of a re-read (changed) file; stat=(mtime, size) is
        recorded so the next scan can skip the file."""
        track = Track()

        if full_path in self.tracks:
            return self.tracks[full_path].insert()

        track.full_path = full_path
        track.basename = basename(full_path)
        track.dir_name = dirname(full_path)
        root_dir = self.get_root_for_path(full_path)
        track.base_dir_name = self.get_short_dir_name(track.dir_name, root_dir)

        if tags is None:
            tags = self._read_local_tags(full_path)
            if tags is None:
                return

        track.duration = int(tags.get("duration") or 0)
        artist = tags.get("artist") or ""
        title = tags.get("title") or ""
        album = tags.get("album") or ""

        if not title:
            clean_name = Path(track.basename).stem
            if len(clean_name.split(" - ")) == 2:
                artist, title = clean_name.split(" - ")
            elif len(clean_name.split("-")) == 2:
                artist, title = clean_name.split("-")
            else:
                title = clean_name
            if artist[:3].isdigit():
                artist = artist[3:].strip()
            elif artist[:2].isdigit():
                artist = artist[2:].strip()

        track.artist = artist
        track.title = title
        track.album = album

        if not track.artist and not track.title:
            track.title = track.basename

        if keep_skipped is not None:
            track.skipped = keep_skipped.skipped

        track.insert()
        if stat is not None:
            self._save_stat(full_path, stat)
