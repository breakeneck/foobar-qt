import os
import eyed3
import database


class Library:
    FOLDER_TABLE_NAME = 'folder'
    TRACK_TABLE_NAME = 'track'

    root_dir: str = ''
    selected_dir = ''
    selected_dir_row = -1

    def __init__(self, dirs):
        self.updateDirs(dirs)
        # init database
        isDbExists = database.connect()
        if not isDbExists:
            Track().create_table()
            Folder().create_table()
        self.scanner = Scanner(self)

    def updateDirs(self, dirs):
        self.root_dir, self.selected_dir, self.selected_dir_row = dirs

    def rescan(self):
        self.scanner.existing_tracks = Track.indexByPath(Track().getAllByPath(self.root_dir, ''))

        database.drop()
        database.connect()

        Track().create_table()
        Folder().create_table()

        self.scanner.parse(self.root_dir)


class Folder(database.Model):
    def __init__(self):
        self.id = 0
        self.path = ''
        self.basename = ''
        self.short_dir_name = ''
        self.parent_dir = ''

    @property
    def tableName(self):
        return Library.FOLDER_TABLE_NAME

    @property
    def indexedAttrs(self):
        return ['path']

    def getAll(self):
        database.db.execute(f'SELECT * FROM {self.tableName} ORDER BY path')
        return map(lambda row: Folder().load(row), database.db.fetchall())


class Track(database.Model):
    def __init__(self):
        self.id = 0
        self.artist = ''
        self.title = ''
        self.album = ''
        self.year = 0
        self.track_num = 0
        self.basename = ''
        self.full_path = ''
        self.dir_name = ''
        self.base_dir_name = ''
        self.duration = 0
        self.skipped = 0

    @staticmethod
    def colCount():
        return 12

    @property
    def indexedAttrs(self):
        return ['artist', 'title', 'dir_name']

    @property
    def tableName(self):
        return Library.TRACK_TABLE_NAME

    def getTitle(self):
        return self.artist + ' - ' + self.title

    def getAttrValues(self):
        return tuple(self.__dict__.values())

    def getAttrLabels(self):
        return [*self.__dict__.keys()]

    def getAllByPath(self, path: str, query: str):
        condition = f'(title LIKE "%{query}%" OR artist LIKE "%{query}%")' if query else ''
        condition += (' AND ' if condition else '') + (f'(dir_name LIKE "{path}%")' if path else '')
        condition += ' ORDER BY full_path'

        database.db.execute(f'SELECT * FROM {self.tableName}' + (f' WHERE {condition}' if condition else ''))
        return map(lambda row: Track().load(row), database.db.fetchall())

    @staticmethod
    def indexByPath(tracks):
        indexed = {}
        for track in tracks:
            indexed[track.full_path] = track
        return indexed

    @staticmethod
    def getPlaylist(library, query=''):
        path = library.selected_dir if library.selected_dir else library.root_dir

        playlist = []
        tracks = []

        current_dir = ''
        for track in Track().getAllByPath(path, query):
            if track.base_dir_name != current_dir:
                current_dir = track.base_dir_name

                dir_row = [''] * (Track.colCount())
                dir_row[0] = current_dir
                playlist.append(tuple(dir_row))
                tracks.append(current_dir)

            playlist.append(track.getAttrValues())
            tracks.append(track)

        return tracks, playlist


class Scanner:
    existing_tracks: {}
    library: Library

    def __init__(self, library):
        self.library = library

    def parse(self, dir_name):
        if dir_name == self.library.root_dir:
            self.insert_dir(dir_name)

        files = os.listdir(dir_name)
        for f in files:
            full_path = os.path.join(dir_name, f)
            if os.path.isdir(full_path):
                self.insert_dir(full_path)

                self.parse(full_path)
            else:
                if full_path in self.existing_tracks:
                    self.existing_tracks[full_path].insert()
                else:
                    self.insert_track(full_path)

    def get_short_dir_name(self, full_path):
        level = full_path.count('/') - self.library.root_dir.count('/')
        if level == 0:
            return '/'
        elif level == 1:
            return '/' + full_path.split('/')[-1]
        else:
            return '/' + '/'.join(full_path.split('/')[-2:])

    def insert_dir(self, full_path):
        folder = Folder()
        folder.path = full_path
        folder.basename = os.path.basename(full_path)
        folder.short_dir_name = self.get_short_dir_name(full_path)
        folder.parent_dir = '' if self.library.root_dir == full_path else os.path.dirname(full_path)
        folder.insert()

    def insert_track(self, full_path):
        track = Track()

        track.full_path = full_path
        track.basename = os.path.basename(full_path)
        track.dir_name = os.path.dirname(full_path)
        track.base_dir_name = self.get_short_dir_name(track.dir_name)

        try:
            file = eyed3.load(full_path)
            track.duration = file.info.time_secs
            if not track.duration:
                return
        except:
            return

        try:
            track.artist = file.tag.artist
            track.title = file.tag.title
            track.album = file.tag.album
        except:
            print('Tag error for file', full_path)

        if not track.artist and not track.title:
            track.title = track.basename

        track.insert()
