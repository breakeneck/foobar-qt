import os
import config
import eyed3
import database

TB_FOLDER = 'folder'
TB_TRACK = 'track'

tracks = []
root_dir = ''


def init(directory):
    global root_dir
    root_dir = directory
    # init database
    is_db_exists = database.connect()
    if not is_db_exists:
        Track().create_table()
        Folder().create_table()


def rescan():
    database.drop()
    database.connect()

    Track().create_table()
    Folder().create_table()

    Scanner().process(root_dir)


class Folder(database.Model):
    def __init__(self):
        self.id = 0
        self.path = ''
        self.basename = ''
        self.short_dir_name = ''
        self.parent_dir = ''

    @property
    def table_name(self):
        return TB_FOLDER

    @property
    def indexed_attributes(self):
        return ['path']

    def get_all(self):
        database.db.execute(f'SELECT * FROM {self.table_name}')
        return map(lambda row: Folder().load(row), database.db.fetchall())


class Track(database.Model):
    # id = 0
    # artist = ''
    # title = ''
    # album = ''
    # year = 0
    # track_num = 0
    # basename = ''
    # full_path = ''
    # dir_name = ''
    # base_dir_name = ''
    # duration = 0
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

    def setAttrs(self, attrs):
        for index, attr in enumerate(self.__dict__):
            # print(index, attr, attrs[index])
            setattr(self, attr, attrs[index])

    @property
    def indexed_attributes(self):
        return ['artist', 'title', 'dir_name']

    @property
    def table_name(self):
        return TB_TRACK

    def to_list(self):
        return [self.id, self.artist, self.title, self.album]

    @staticmethod
    def headings():
        return ['id', 'artist', 'title', 'album']

    @staticmethod
    def col_width():
        return [5, 30, 30, 30]

    def get_all_by_path(self, full_path):
        database.db.execute(f'SELECT * FROM {self.table_name} WHERE dir_name LIKE "{full_path}%"')
        return map(lambda row: Track().load(row), database.db.fetchall())

    @staticmethod
    def get_playlist(full_path=None):
        global tracks
        full_path = root_dir if full_path is None else full_path

        playlist = []
        row_colors = []
        tracks.clear()

        current_dir = ''
        for track in Track().get_all_by_path(full_path):
            if track.base_dir_name != current_dir:
                current_dir = track.base_dir_name

                tracks.append(current_dir)
                playlist.append(['', current_dir])
                row_colors.append([len(tracks) - 1, '#000000', '#ffffff'])

            tracks.append(track)
            playlist.append(track.to_list())

        return playlist, row_colors


class Scanner:
    def process(self, dir_name):
        if dir_name == root_dir:
            self.insert_dir(dir_name)

        files = os.listdir(dir_name)
        for f in files:
            full_path = os.path.join(dir_name, f)
            if os.path.isdir(full_path):
                self.insert_dir(full_path)

                self.process(full_path)
            else:
                # pass
                self.insert_track(full_path)

    @staticmethod
    def get_short_dir_name(full_path):
        level = full_path.count('/') - root_dir.count('/')
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
        folder.parent_dir = '' if root_dir == full_path else os.path.dirname(full_path)
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
