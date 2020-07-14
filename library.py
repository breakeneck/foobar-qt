import faulthandler
faulthandler.enable()

import os
import eyed3
import database
import player
from random import randint
from PyQt5 import QtGui, QtCore, QtWidgets

TB_FOLDER = 'folder'
TB_TRACK = 'track'

# tracks = []
root_dir = ''
selected_dir = ''


def init(dirs):
    updateDirs(dirs)
    # init database
    is_db_exists = database.connect()
    if not is_db_exists:
        Track().create_table()
        Folder().create_table()


def updateDirs(dirs):
    global root_dir, selected_dir
    root_dir, selected_dir = dirs


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
    def tableName(self):
        return TB_FOLDER

    @property
    def indexedAttrs(self):
        return ['path']

    def getAll(self):
        database.db.execute(f'SELECT * FROM {self.tableName}')
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

    @staticmethod
    def colCount():
        return 11

    @property
    def indexedAttrs(self):
        return ['artist', 'title', 'dir_name']

    @property
    def tableName(self):
        return TB_TRACK

    def getAttrValues(self):
        return tuple(self.__dict__.values())

    def getAttrLabels(self):
        return [*self.__dict__.keys()]

    def getAllByPath(self, path, query):
        condition = f'(title LIKE "%{query}%" OR artist LIKE "%{query}%")' if query else ''
        # print(condition)
        condition += (' AND ' if condition else '') + (f'(dir_name LIKE "{path}%")' if path else '')
        # print(condition)

        database.db.execute(f'SELECT * FROM {self.tableName}' + (f' WHERE {condition}' if condition else ''))
        return map(lambda row: Track().load(row), database.db.fetchall())

    @staticmethod
    def getPlaylist(query=''):
        path = selected_dir if selected_dir else root_dir

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


class TreeModel(QtGui.QStandardItemModel):
    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)
        self.loadTreeData()

    def loadTreeData(self):
        self.clear()

        for folder in Folder().getAll():
            parent = self.invisibleRootItem()
            for word in folder.path[len(os.path.dirname(root_dir)):].split("/")[1:]:
                for i in range(parent.rowCount()):
                    item = parent.child(i)
                    if item.text() == word:
                        it = item
                        break
                else:
                    it = QtGui.QStandardItem(word)
                    parent.setChild(parent.rowCount(), it)
                parent = it

        self.updateTitle()

    def updateTitle(self):
        self.setHeaderData(0, QtCore.Qt.Horizontal, root_dir)

    @staticmethod
    def getDirPath(index: QtCore.QModelIndex):
        folder = []
        while index.isValid():
            folder.append(index.data())
            index = index.parent()
        return os.path.dirname(root_dir) + '/' + '/'.join(folder[::-1])


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self):
        super(TableModel, self).__init__()
        self.headers = Track().getAttrLabels()
        self.groupRows = []
        self.tracks = []
        self.rows = []
        self.query = ''

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=None):
        if role == QtCore.Qt.FontRole and index.row() in self.groupRows:
            font = QtGui.QFont()
            font.setBold(True)
            return font
        # } else if (role == Qt::ForegroundRole & & index.column() == 0) {
        # return QColor(Qt::red);
        # }
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        return self.rows[index.row()][index.column()]

    def headerData(self, section, orientation, role=None):
        if role != QtCore.Qt.DisplayRole or orientation != QtCore.Qt.Horizontal:
            return QtCore.QVariant()
        return self.headers[section]

    def refreshPlaylist(self, query=''):
        self.query = ''
        self.tracks, self.rows = Track().getPlaylist(query)

        self.modelAboutToBeReset.emit()
        self.groupRows.clear()
        for row, item in enumerate(self.tracks):
            if isinstance(item, str):
                self.groupRows.append(row)

        self.modelReset.emit()

    def getNowPlayIndex(self):
        trackId = player.now_playing.id
        for row, track in enumerate(self.tracks):
            if isinstance(track, Track) and track.id == trackId:
                return self.index(row, 0)
        return False


    def getNextIndex(self):
        if not self.getNextRow():
            return False

        while not isinstance(self.tracks[player.now_playing_row], Track):
            if not self.getNextRow():
                return False

        return self.index(player.now_playing_row, 0)

    def getNextRow(self):
        if player.now_playing_row < len(self.tracks) - 1:
            player.now_playing_row += 1
            return True
        else:
            return False

    def getPrevIndex(self):
        if not self.getPrevRow():
            return False

        while not isinstance(self.tracks[player.now_playing_row], Track):
            if not self.getPrevRow():
                return False

        return self.index(player.now_playing_row, 0)

    def getPrevRow(self):
        if player.now_playing_row > 0:
            player.now_playing_row -= 1
            return True
        else:
            return False

    def getRndIndex(self):
        if not len(self.tracks):
            return False

        index = randint(0, len(self.tracks) - 1)
        while not isinstance(self.tracks[index], Track):
            index = randint(0, len(self.tracks) - 1)

        player.now_playing_row = index
        return self.index(player.now_playing_row, 0)
