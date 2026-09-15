import os
import random

import database
import qtawesome as qta
from PyQt6 import QtCore, QtGui, QtWidgets

from library import Folder, Library, Track
from player import Player
from virtualfs import dirname


# qtawesome glyphs must follow the palette: fixed white glyphs are invisible
# on light themes and black ones on dark themes
ICON_NAMES = {
    "nextBtn": "mdi.skip-next",
    "prevBtn": "mdi.skip-previous",
    "nextRndBtn": "mdi.chevron-right",
    "stopAfterBtn": "mdi.radio-off",
    "rndOrderBtn": "mdi.playlist-play",
    "browseDirBtn": "mdi.folder-open",
    "rescanLibBtn": "mdi.refresh",
    "expandBtn": "mdi.arrow-expand-vertical",
    "settingsBtn": "mdi.cog",
    "followTreeView": "mdi.circle",
}


_last_icon_color = None


def themed_icon(widget, name):
    # read the widget's effective palette so per-widget overrides and
    # app/system palette changes are both picked up
    color = widget.palette().color(QtGui.QPalette.ColorRole.ButtonText)
    return qta.icon(name, color=color.name())


def rethemeIcons(main):
    # PaletteChange events can arrive repeatedly; only re-render when the
    # glyph color actually changed
    global _last_icon_color
    color = main.palette().color(QtGui.QPalette.ColorRole.ButtonText).name()
    if color == _last_icon_color:
        return
    _last_icon_color = color
    for attr, name in ICON_NAMES.items():
        getattr(main, attr).setIcon(qta.icon(name, color=color))
    # playBtn's icon depends on the playback state
    main.updatePlayStatus()


def postSetup(main):
    main.timer = QtCore.QTimer(main)
    main.treeModel = TreeModel(main)
    main.treeModel.setLibrary(main.library)
    main.tableModel = TableModel()
    main.tableModel.setLibrary(main.library)
    main.tableModel.setPlayer(main.player)
    main.statusbar = StatusBar()
    main.timer.setInterval(100)
    main.statusbar.setObjectName("statusbar")
    main.setStatusBar(main.statusbar)
    main.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
    main.lyricsCombo.addItems(main.lyrics.PROVIDERS)
    main.posSlider.setMaximum(1000)
    main.treeView.setModel(main.treeModel)
    main.tableView.setModel(main.tableModel)
    main.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    main.volumeSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, main)
    main.volumeSlider.setMaximum(100)
    main.volumeSlider.setValue(main.player.getVolume())
    main.volumeSlider.setToolTip("Volume")
    main.volumeSlider.setFixedWidth(100)
    main.statusbar.addPermanentWidget(main.volumeSlider)
    main.searchEdit.setFocusPolicy(QtCore.Qt.StrongFocus)
    main.tableView.setFocusPolicy(QtCore.Qt.StrongFocus)
    rethemeIcons(main)


class TreeModel(QtGui.QStandardItemModel):
    library: Library

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)
        self.folders = []

    def setLibrary(self, library):
        self.library = library

    def loadTreeData(self, treeView: QtWidgets.QTreeView):
        self.clear()

        # The tree shows the full folder hierarchy starting at each library
        # root (the target dir). Folders that contain no tracks anywhere in
        # their subtree (e.g. 'covers' image dirs) are hidden.
        database.db.execute(
            f"SELECT DISTINCT dir_name FROM {Library.TRACK_TABLE_NAME}"
        )
        leaf_dirs = {row[0] for row in database.db.fetchall()}
        all_roots = self.library.getAllRootDirs()

        def root_for(path):
            for root in all_roots:
                if path == root or path.startswith(root + "/"):
                    return root
            return ""

        # every folder on the way from a root down to a dir containing tracks
        visible = set(all_roots)
        for leaf in leaf_dirs:
            path = leaf
            while path and root_for(path):
                visible.add(path)
                parent = dirname(path)
                if parent == path:
                    break
                path = parent

        root_items = {}
        items_by_path = {}
        for folder in Folder().getAll():  # ORDER BY path: parents before children
            path = folder.path
            root = root_for(path)
            if not root or path not in visible:
                continue

            if path == root:
                parent = self.invisibleRootItem()
                text = folder.getRelPath(self.library)
            else:
                parent = items_by_path.get(dirname(path)) or root_items.get(root)
                if parent is None:
                    continue  # the root row is missing from the folder table
                text = folder.basename

            item = FolderItem(text)
            item.setDbModel(folder)
            parent.setChild(parent.rowCount(), item)
            if folder.is_expanded:
                treeView.expand(item.index())
            else:
                treeView.collapse(item.index())
            items_by_path[path] = item
            if path == root:
                root_items[root] = item

        self.updateTitle()

    def iterItems(self, root):
        if root is not None:
            stack = [root]
            while stack:
                parent = stack.pop(0)
                for row in range(parent.rowCount()):
                    for column in range(parent.columnCount()):
                        child = parent.child(row, column)
                        yield child
                        if child.hasChildren():
                            stack.append(child)

    def updateTitle(self):
        self.setHeaderData(0, QtCore.Qt.Orientation.Horizontal, self.library.root_dir)

    def getFolder(self, index):
        return self.folders

    def getDirPath(self, index: QtCore.QModelIndex):
        folder = []
        while index.isValid():
            folder.append(index.data())
            index = index.parent()
        return os.path.dirname(self.library.root_dir) + "/" + "/".join(folder[::-1])


class FolderItem(QtGui.QStandardItem):
    dbModel: Folder

    def setDbModel(self, dbModel):
        self.dbModel = dbModel


class TableModel(QtCore.QAbstractTableModel):
    library: Library
    player: Player

    def __init__(self):
        super(TableModel, self).__init__()
        self.headers = Track().getAttrLabels()
        self.groupRows = []
        self.tracks = []
        self.rows = []
        self.query = ""

    def setLibrary(self, library):
        self.library = library

    def setPlayer(self, player):
        self.player = player

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def flags(self, index):
        # group header rows are decorative: letting them be selected would
        # pass a dir name where a Track is expected (play/Enter/statusbar)
        if index.row() in self.groupRows:
            return QtCore.Qt.ItemFlag.ItemIsEnabled
        return super().flags(index)

    def data(self, index, role=None):
        if role == QtCore.Qt.ItemDataRole.FontRole:
            if index.row() in self.groupRows:
                font = QtGui.QFont()
                font.setBold(True)
                return font
            elif self.tracks[index.row()].skipped:
                font = QtGui.QFont()
                font.setStrikeOut(True)
                return font
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        return self.rows[index.row()][index.column()]

    def headerData(self, section, orientation, role=None):
        if (
            role != QtCore.Qt.ItemDataRole.DisplayRole
            or orientation != QtCore.Qt.Orientation.Horizontal
        ):
            return None
        return self.headers[section]

    def refreshPlaylist(self, query=""):
        self.query = query
        # query must not be passed positionally: the 2nd arg is root_dir
        self.tracks, self.rows = Track().getPlaylist(self.library, None, query)

        self.modelAboutToBeReset.emit()
        self.groupRows.clear()
        for row, item in enumerate(self.tracks):
            if isinstance(item, str):
                self.groupRows.append(row)

        self.modelReset.emit()

    def getNowPlayIndex(self):
        if not self.player.now_playing:
            return False

        trackId = self.player.now_playing.id
        for row, track in enumerate(self.tracks):
            if isinstance(track, Track) and track.id == trackId:
                self.player.now_playing_row = row
                return self.index(row, 0)
        self.player.now_playing_row = -1
        return False

    def getNextIndex(self):
        while self.player.now_playing_row < len(self.tracks) - 1:
            self.player.now_playing_row += 1

            item = self.tracks[self.player.now_playing_row]
            if isinstance(item, Track) and not item.skipped:
                return self.index(self.player.now_playing_row, 0)

        return False

    def getPrevIndex(self):
        self.getNowPlayIndex()
        if not self.getPrevRow():
            return False

        while not isinstance(self.tracks[self.player.now_playing_row], Track):
            if not self.getPrevRow():
                return False

        return self.index(self.player.now_playing_row, 0)

    def getPrevRow(self):
        if self.player.now_playing_row > 0:
            self.player.now_playing_row -= 1
            return True
        else:
            return False

    def getRndIndex(self):
        notSkippedTracks = {}
        for index, track in enumerate(self.tracks):
            if isinstance(track, Track) and not track.skipped:
                notSkippedTracks[index] = track

        if not len(notSkippedTracks):
            return False

        index = random.choice(list(notSkippedTracks.keys()))

        self.player.now_playing_row = index
        return self.index(self.player.now_playing_row, 0)


class StatusBar(QtWidgets.QStatusBar):
    clicked = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
