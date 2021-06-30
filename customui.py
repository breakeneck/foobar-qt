import os
import player
from library import Library, Folder, Track
from random import randint
from PyQt5 import QtGui, QtCore, QtWidgets


class TreeModel(QtGui.QStandardItemModel):
    library: Library

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)
        self.folders = []

    def setLibrary(self, library):
        self.library = library
        self.loadTreeData()

    def loadTreeData(self):
        self.clear()

        for folder in Folder().getAll():
            parent = self.invisibleRootItem()
            for word in folder.path[len(os.path.dirname(self.library.root_dir)):].split("/")[1:]:
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
        self.setHeaderData(0, QtCore.Qt.Horizontal, self.library.root_dir)

    def getDirPath(self, index: QtCore.QModelIndex):
        folder = []
        while index.isValid():
            folder.append(index.data())
            index = index.parent()
        return os.path.dirname(self.library.root_dir) + '/' + '/'.join(folder[::-1])


class TableModel(QtCore.QAbstractTableModel):
    library: Library

    def __init__(self):
        super(TableModel, self).__init__()
        self.headers = Track().getAttrLabels()
        self.groupRows = []
        self.tracks = []
        self.rows = []
        self.query = ''

    def setLibrary(self, library):
        self.library = library

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=None):
        if role == QtCore.Qt.FontRole:
            if index.row() in self.groupRows:
                font = QtGui.QFont()
                font.setBold(True)
                return font
            elif self.tracks[index.row()].skipped:
                font = QtGui.QFont()
                font.setStrikeOut(True)
                return font
        # } else if (role == Qt::ForegroundRole & & index.column() == 0) {
        # return QColor(Qt::red);
        # }
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        return self.rows[index.row()][index.column()]
        # return self.tracks[index.row()][index.column()]

    def headerData(self, section, orientation, role=None):
        if role != QtCore.Qt.DisplayRole or orientation != QtCore.Qt.Horizontal:
            return QtCore.QVariant()
        return self.headers[section]

    def refreshPlaylist(self, query=''):
        self.query = ''
        self.tracks, self.rows = Track().getPlaylist(self.library, query)

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
                player.now_playing_row = row
                return self.index(row, 0)
        player.now_playing_row = -1
        return False

    def getNextIndex(self):
        while player.now_playing_row < len(self.tracks):
            player.now_playing_row += 1

            item = self.tracks[player.now_playing_row]
            if isinstance(item, Track) and not item.skipped:
                return self.index(player.now_playing_row, 0)

        return False

    def getPrevIndex(self):
        self.getNowPlayIndex()  # Refresh player.now_playing_row
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


class StatusBar(QtWidgets.QStatusBar):
    clicked = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
