from PyQt5 import QtWidgets, QtCore, QtSql, Qt

from main import FooQt
from custom_widgets import StatusBar
import library
import player
from config import Config

import qtawesome as qta


class MainUiSetup:
    def tune(self, main: FooQt):
        self._addInvisibleElements(main)
        self._fillComboBoxes(main)
        self._setStatusBar(main)
        self._setIcons(main)
        
        self._setupSlider(main)
        self._loadDirectoryTree(main)


    @staticmethod
    def _addInvisibleElements(main: FooQt):
        main.timer = QtCore.QTimer(main)
        main.treeModel = library.TreeModel()
        main.tableModel = library.TableModel()
        main.statusbar = StatusBar()

    @staticmethod
    def _fillComboBoxes(main: FooQt):
        main.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
        # main.lyricsCombo.addItems(main.lyrics.PROVIDERS)

    @staticmethod
    def _setupSlider(main: FooQt):
        main.timer.setInterval(100)
        main.posSlider.setMaximum(1000)

    @staticmethod
    def _setIcons(main: FooQt):
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

    @staticmethod
    def getPlayIcon():
        return qta.icon('fa.play')

    @staticmethod
    def getPauseIcon():
        return qta.icon('fa.pause')

    @staticmethod
    def _setStatusBar(main: FooQt):
        main.statusbar.setObjectName("statusbar")
        main.setStatusBar(main.statusbar)

        main.volumeSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal, main)
        main.volumeSlider.setMaximum(100)
        main.volumeSlider.setValue(player.getVolume())
        main.volumeSlider.setToolTip("Volume")
        main.volumeSlider.setFixedWidth(100)
        main.statusbar.addPermanentWidget(main.volumeSlider)

    @staticmethod
    def _loadDirectoryTree(main: FooQt):
        main.treeView.setModel(main.treeModel)


    @staticmethod
    def connectEvents(main: FooQt, app: QtWidgets.QApplication):
        main.themeCombo.activated.connect(lambda: app.setStyle(main.themeCombo.currentText()))
        main.lyricsCombo.activated.connect(lambda: main.lyrics.setProvider(main.lyricsCombo.currentText()))
        main.browseDirBtn.clicked.connect(main.browseDirClick)
        main.rescanLibBtn.clicked.connect(main.rescanLibrary)
        main.settingsBtn.clicked.connect(main.openSettingsDialog)
        main.playBtn.clicked.connect(main.playBtnClick)
        main.nextBtn.clicked.connect(main.next)
        main.prevBtn.clicked.connect(main.prev)
        main.nextRndBtn.clicked.connect(main.nextRnd)
        main.searchEdit.textChanged.connect(main.searchChanged)
        main.treeView.clicked.connect(main.treeViewClick)
        main.tableView.doubleClicked.connect(main.play)
        main.posSlider.sliderMoved.connect(main.setPos)
        main.posSlider.sliderPressed.connect(main.setPos)
        main.timer.timeout.connect(main.updatePos)
        main.tableModel.modelAboutToBeReset.connect(main.tableModelBeforeChanged)
        main.tableModel.modelReset.connect(main.tableModelChanged)
        main.statusbar.clicked.connect(main.selectCurrentTrack)
        main.expandBtn.clicked.connect(main.expandBtnClick)
        main.volumeSlider.valueChanged.connect(main.setVolume)

    @staticmethod
    def loadUiState(main: FooQt, app: QtWidgets.QApplication):
        main.config.updateUiSizes(app)
        
    @staticmethod
    def initPlaylist(main: FooQt):
        main.tableView.setModel(main.tableModel)
        main.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        main.tableModel.refreshPlaylist('')