import os
from player import Player
from library import Library, Folder, Track
from random import randint
from PyQt5 import QtGui, QtCore, QtWidgets
import qtawesome as qta


def postSetup(main):
    # add invisible elements
    main.timer = QtCore.QTimer(main)
    main.treeModel = TreeModel(main)
    main.treeModel.setLibrary(main.library)
    main.tableModel = TableModel()
    main.tableModel.setLibrary(main.library)
    main.tableModel.setPlayer(main.player)
    main.statusbar = StatusBar()
    # update qtDesigner non available properties
    main.timer.setInterval(100)
    # design updates
    main.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
    main.lyricsCombo.addItems(main.lyrics.PROVIDERS)
    main.playBtn.setIcon(qta.icon('fa.play'))
    main.nextBtn.setIcon(qta.icon('mdi.skip-next'))
    main.prevBtn.setIcon(qta.icon('mdi.skip-previous'))
    main.nextRndBtn.setIcon(qta.icon('fa.question'))
    main.stopAfterBtn.setIcon(qta.icon('fa.stop-circle'))
    main.rndOrderBtn.setIcon(qta.icon('fa.random'))
    main.browseDirBtn.setIcon(qta.icon('fa.folder-open'))
    main.rescanLibBtn.setIcon(qta.icon('mdi.refresh'))
    main.expandBtn.setIcon(qta.icon('mdi.arrow-expand-vertical'))
    main.settingsBtn.setIcon(qta.icon('fa.cog'))

    # main.skipShortcut.activated.connect((lambda : QtWidgets.QMessageBox.information(main, 'Message', 'Track "' + main.getSelectedTrack().getTitle() + '" will be skipped')))
    main.posSlider.setMaximum(1000)
    # load Directory tree
    main.treeView.setModel(main.treeModel)
    # load Tracks
    main.tableView.setModel(main.tableModel)
    main.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    # my custom statusbar
    main.statusbar.setObjectName("statusbar")
    main.setStatusBar(main.statusbar)
    # statusbar widgets
    main.volumeSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal, main)
    main.volumeSlider.setMaximum(100)
    main.volumeSlider.setValue(main.player.getVolume())
    main.volumeSlider.setToolTip("Volume")
    main.volumeSlider.setFixedWidth(100)
    main.statusbar.addPermanentWidget(main.volumeSlider)
    # search edit params
    main.searchEdit.setFocusPolicy(QtCore.Qt.StrongFocus)
    main.tableView.setFocusPolicy(QtCore.Qt.StrongFocus)


class TreeWidget(QtWidgets.QTreeWidget):
    currentTextChanged = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super(TreeWidget, self).__init__(parent)
        self.currentItemChanged.connect(self.onCurrentItemChanged)
        self.setHeaderLabel('Standard Section Library')
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.readSettings()
        self.expandAll()

    def onCurrentItemChanged(self, current, previous):
        if current not in [self.topLevelItem(ix) for ix in range(self.topLevelItemCount())]:
            self.currentTextChanged.emit(current.text(0))

    def readSettings(self):
        settings = QtCore.QSettings()
        settings.beginGroup("TreeWidget")
        values = settings.value("items")
        if values is None:
            self.loadDefault()
        else:
            TreeWidget.dataToChild(values, self.invisibleRootItem())
            self.customized_item = None
            for ix in range(self.topLevelItemCount()):
                tlevel_item = self.topLevelItem(ix)
                if tlevel_item.text(0) == "Customized":
                    self.customized_item = tlevel_item
        settings.endGroup()

    def writeSettings(self):
        settings = QtCore.QSettings()
        settings.beginGroup("TreeWidget")
        settings.setValue("items", TreeWidget.dataFromChild(self.invisibleRootItem()))
        settings.endGroup()

    def loadDefault(self):
        standardsectionlist = ["D100", "D150", "D200", "D250", "D300", "D350", "D400", "D450", "D500",
                               "D550", "D600", "D650", "D700", "D750", "D800", "D850", "D900", "D950", "D1000"]
        rootItem = QtWidgets.QTreeWidgetItem(self, ['Circular shapes'])
        # rootItem.setIcon(0, QtGui.QIcon(os.path.join(iconroot, "images/circularcolumnnorebar.png")))
        for element in standardsectionlist:
            rootItem.addChild(QtWidgets.QTreeWidgetItem([element]))

        self.customized_item = QtWidgets.QTreeWidgetItem(self, ["Customized"])
        # self.customized_item.setIcon(0, QtGui.QIcon(os.path.join(iconroot, "images/circularcolumnnorebar.png")))

    @staticmethod
    def dataToChild(info, item):
        TreeWidget.tupleToItem(info["data"], item)
        for val in info["childrens"]:
            child = QtWidgets.QTreeWidgetItem()
            item.addChild(child)
            TreeWidget.dataToChild(val, child)

    @staticmethod
    def tupleToItem(t, item):
        # set values to item
        ba, isSelected = t
        ds = QtCore.QDataStream(ba)
        ds >> item
        item.setSelected(isSelected)

    @staticmethod
    def dataFromChild(item):
        l = []
        for i in range(item.childCount()):
            child = item.child(i)
            l.append(TreeWidget.dataFromChild(child))
        return {"childrens": l, "data": TreeWidget.itemToTuple(item)}

    @staticmethod
    def itemToTuple(item):
        # return values from item
        ba = QtCore.QByteArray()
        ds = QtCore.QDataStream(ba, QtCore.QIODevice.WriteOnly)
        ds << item
        return ba, item.isSelected()


class TreeModel(QtGui.QStandardItemModel):
    library: Library

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)
        self.folders = []

    def setLibrary(self, library):
        self.library = library

    def loadTreeData(self, treeView: QtWidgets.QTreeView):
        self.clear()

        for folder in Folder().getAll():
            parent = self.invisibleRootItem()
            for word in folder.getRelPath(self.library).split("/"):

                for i in range(parent.rowCount()):
                    child = parent.child(i)
                    if child.text() == word:
                        item = child
                        break
                else:
                    item = FolderItem(word)
                    item.setDbModel(folder)

                    parent.setChild(parent.rowCount(), item)
                    if item.dbModel.is_expanded:
                        treeView.expand(item.index())
                    else:
                        treeView.collapse(item.index())
                parent = item

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
        self.setHeaderData(0, QtCore.Qt.Horizontal, self.library.root_dir)

    def getFolder(self, index):
        return self.folders

    def getDirPath(self, index: QtCore.QModelIndex):
        folder = []
        while index.isValid():
            folder.append(index.data())
            index = index.parent()
        return os.path.dirname(self.library.root_dir) + '/' + '/'.join(folder[::-1])


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
        self.query = ''

    def setLibrary(self, library):
        self.library = library

    def setPlayer(self, player):
        self.player = player

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
        while self.player.now_playing_row < len(self.tracks):
            self.player.now_playing_row += 1

            item = self.tracks[self.player.now_playing_row]
            if isinstance(item, Track) and not item.skipped:
                return self.index(self.player.now_playing_row, 0)

        return False

    def getPrevIndex(self):
        self.getNowPlayIndex()  # Refresh self.player.now_playing_row
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
        if not len(self.tracks):
            return False

        index = randint(0, len(self.tracks) - 1)
        while not isinstance(self.tracks[index], Track):
            index = randint(0, len(self.tracks) - 1)

        self.player.now_playing_row = index
        return self.index(self.player.now_playing_row, 0)


class StatusBar(QtWidgets.QStatusBar):
    clicked = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
