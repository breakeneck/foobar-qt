import os
from pathlib import Path

import eyed3

import database
from virtualfs import (
    basename,
    dirname,
    get_root_label,
    get_tree_path,
    is_sftp_path,
    isdir,
    isfile,
    join,
    listdir,
    open_file_to_temp,
    parse_sftp_url,
)


class Library:
    FOLDER_TABLE_NAME = "folder"
    TRACK_TABLE_NAME = "track"

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
        self.scanner = Scanner(self)

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

    def getAllRootDirs(self):
        if self.library_dirs:
            return self.library_dirs
        return [self.root_dir] if self.root_dir else []

    def rescan(self):
        all_dirs = self.getAllRootDirs()
        self.scanner.existing_tracks = {}
        for root in all_dirs:
            tracks = Track().getAllByPath(root, "")
            for t in tracks:
                self.scanner.existing_tracks[t.full_path] = t
        self.scanner.tracks = {}

        database.drop()
        database.connect()

        Track().create_table()
        Folder().create_table()

        for root in all_dirs:
            self.scanner.parse(root)
        self.scanner.tracks = []


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
        condition = (
            f'(title LIKE "%{query}%" OR artist LIKE "%{query}%")' if query else ""
        )
        condition += (" AND " if condition else "") + (
            f'(dir_name LIKE "{path}%")' if path else ""
        )
        condition += " ORDER BY full_path"

        database.db.execute(
            f"SELECT * FROM {self.tableName}"
            + (f" WHERE {condition}" if condition else "")
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
    existing_tracks: {}
    library: Library
    tracks = {}

    def __init__(self, library):
        self.library = library

    def parse(self, dir_name):
        all_roots = self.library.getAllRootDirs()
        if dir_name in all_roots:
            self.insert_dir(dir_name)

        files = listdir(dir_name)
        for f in files:
            full_path = join(dir_name, f)
            if isdir(full_path):
                self.insert_dir(full_path)
                self.parse(full_path)
            else:
                if isfile(full_path):
                    if full_path in self.existing_tracks:
                        self.existing_tracks[full_path].insert()
                    else:
                        self.insert_track(full_path)

    def get_root_for_path(self, full_path):
        """Find which root dir this path belongs to."""
        for root in self.library.getAllRootDirs():
            if full_path.startswith(root):
                return root
        return ""

    def get_short_dir_name(self, full_path, root_dir):
        """
        Compute display name for track grouping in the table view.
        For SFTP: 'ha://music/Artist' or 'ha://music' for the root itself.
        For local: 'Music/Artist' or 'Music' for the root itself.
        """
        root_label = get_root_label(root_dir)
        if full_path == root_dir:
            return root_label
        if full_path.startswith(root_dir):
            rel = full_path[len(root_dir) :].lstrip("/")
            return root_label + "/" + rel
        return basename(full_path)

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

    def insert_track(self, full_path):
        track = Track()

        if full_path in self.tracks:
            return self.tracks[full_path].insert()

        track.full_path = full_path
        track.basename = basename(full_path)
        track.dir_name = dirname(full_path)
        root_dir = self.get_root_for_path(full_path)
        track.base_dir_name = self.get_short_dir_name(track.dir_name, root_dir)

        try:
            local_path, is_temp = open_file_to_temp(full_path)
            try:
                file = eyed3.load(local_path)
                track.duration = file.info.time_secs
                if not track.duration:
                    return
            finally:
                if is_temp:
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
        except:
            print("Critical error on loading tag for", full_path)
            return

        try:
            track.artist = file.tag.artist
            track.title = (
                file.tag.title if file.tag.title else Path(track.basename).stem
            )
            track.album = file.tag.album
        except:
            if not track.title:
                clean_name = Path(track.basename).stem
                if len(clean_name.split(" - ")) == 2:
                    track.artist, track.title = clean_name.split(" - ")
                elif len(clean_name.split("-")) == 2:
                    track.artist, track.title = clean_name.split("-")
                else:
                    track.title = clean_name
                if track.artist[:3].isdigit():
                    track.artist = track.artist[3:].strip()
                elif track.artist[:2].isdigit():
                    track.artist = track.artist[2:].strip()
            print("Tag error for file", full_path)

        if not track.artist and not track.title:
            track.title = track.basename

        track.insert()
