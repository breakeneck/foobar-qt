import json
import sys
import time

import keyboard
import qtawesome as qta
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QIcon, QShortcut

import config
import customui
import design
from dialogs import AddLibraryDirDialog, SettingsDialog
from lastfm import LastFM
from library import Library, Track
from lyrics import Lyrics
from player import Player
from sftp import get_sftp_manager


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)

        # config loading
        self.config = config.Config(self)
        self.library = Library(self.config.getLibraryDirs())
        self.player = Player()
        self.lyrics = Lyrics()
        self.lyricsThread = None
        self.lastfm = LastFM(self.config)

        # make post ui setup after library is initialized
        customui.postSetup(self)

        # Load config goes after postSetupUi() to be able to restore columns width
        self.config.load(app)
        self.connectEvents(app)

        self.tableModel.refreshPlaylist(self.searchEdit.text())
        self.treeModel.loadTreeData(self.treeView)

    def connectEvents(self, app):
        self.themeCombo.activated.connect(
            lambda: app.setStyle(self.themeCombo.currentText())
        )
        self.lyricsCombo.activated.connect(self.changeLyricsProvider)
        self.browseDirBtn.clicked.connect(self.browseDirClick)
        self.rescanLibBtn.clicked.connect(self.rescanLibrary)
        self.settingsBtn.clicked.connect(self.openSettingsDialog)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.nextBtn.clicked.connect(self.next)
        self.prevBtn.clicked.connect(self.prev)
        self.nextRndBtn.clicked.connect(self.nextRnd)
        self.searchEdit.textChanged.connect(self.searchChanged)
        self.searchEdit.returnPressed.connect(self.stopAndPlay)
        self.searchClearBtn.clicked.connect(self.searchClear)
        self.treeView.clicked.connect(self.treeViewClick)
        self.tableView.doubleClicked.connect(self.play)
        self.posSlider.sliderMoved.connect(self.setPos)
        self.posSlider.sliderPressed.connect(self.setPos)
        self.timer.timeout.connect(self.updatePos)
        self.tableModel.modelAboutToBeReset.connect(self.tableModelBeforeChanged)
        self.tableModel.modelReset.connect(self.tableModelChanged)
        self.statusbar.clicked.connect(self.selectCurrentTrack)
        self.expandBtn.clicked.connect(self.expandBtnClick)
        self.volumeSlider.valueChanged.connect(self.setVolume)
        self.followTreeView.clicked.connect(self.locateCurrentFolder)
        # shortcuts
        QShortcut(QtGui.QKeySequence("Ctrl+S"), self).activated.connect(self.skipTrack)
        QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self).activated.connect(
            self.playBtnClick
        )
        QShortcut(QtGui.QKeySequence("Ctrl+H"), self).activated.connect(
            self.showMinimized
        )
        QShortcut(QtGui.QKeySequence("Ctrl+F"), self).activated.connect(self.goToSearch)

    def showEvent(self, a0: QtGui.QShowEvent) -> None:
        self.config.onAppShow()

    def locateCurrentFolder(self):
        if not self.player.now_playing:
            return

        self.treeView.collapseAll()

        parent = self.treeModel.invisibleRootItem()
        for word in (
            self.player.now_playing.getFolder().getRelPath(self.library).split("/")
        ):
            print("searching for word", word)
            for i in range(parent.rowCount()):
                child = parent.child(i)
                if child.text() == word:
                    print(word, child.index())
                    self.treeView.expand(child.index())
                    self.treeView.setCurrentIndex(child.index())
                    parent = child
                    break

        self.treeViewClick(parent.index())
        self.selectCurrentTrack()

    def expandBtnClick(self):
        if self.expandBtn.isChecked():
            rootIndex = self.treeModel.index(0, 0)
            self.treeView.expand(rootIndex)
            for row in range(self.treeModel.rowCount(rootIndex)):
                index = rootIndex.child(row, 0)
                self.treeView.expand(index)
        else:
            self.treeView.collapseAll()

    def goToSearch(self):
        self.searchEdit.setText("")
        self.searchEdit.setFocus()

    def treeViewClick(self, index: QtCore.QModelIndex):
        self.library.selected_dir_row = index.row()
        self.library.selected_dir = self.treeModel.itemFromIndex(index).dbModel.path
        self.config.updateSelectedDir(
            self.library.selected_dir, self.library.selected_dir_row
        )
        self.searchChanged()

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        if e.key() == QtCore.Qt.Key_Escape:
            self.searchClear()
        pass

    def searchChanged(self):
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def searchClear(self):
        self.searchEdit.setText("")
        self.selectCurrentTrack()
        self.tableView.setFocus()

    def stop(self):
        self.player.stop()
        self.updatePlayStatus()

    def updatePlayStatus(self):
        icon = (
            qta.icon("mdi.play") if self.player.isNoMusic() else qta.icon("mdi.pause")
        )
        self.playBtn.setIcon(icon)
        if self.player.isNoMusic():
            self.timer.stop()
        else:
            self.timer.start()
        self.statusbar.showMessage(self.player.getNowPlayingMsg())

    def selectCurrentTrack(self):
        currentIndex = self.tableModel.getNowPlayIndex()
        if currentIndex is not False:
            self.tableView.setCurrentIndex(currentIndex)
        else:
            print("can't move to current index, because its false")

    def stopAndPlay(self):
        self.player.stop()
        self.tableView.clearSelection()
        self.playBtnClick()

    def playBtnClick(self):
        if not self.player.now_playing:
            index = self.tableView.selectedIndexes()
            if not index:
                index = [self.tableModel.getNextIndex()]
            return self.play((index or [None])[0])

        self.player.playPause()
        self.updatePlayStatus()

    def play(self, index: QtCore.QModelIndex = None):
        if not index:
            return print("No item selected")

        track = self.player.play(index.row(), self.tableModel.tracks[index.row()])
        if track:
            self.selectCurrentTrack()
            self.updatePlayStatus()
            self.findLyrics()
            try:
                self.lastfm.updateNowPlaying(
                    self.player.now_playing.artist, self.player.now_playing.title
                )
            except Exception as e:
                print(str(e))

    def changeLyricsProvider(self, text):
        self.config.setLyricsProvider(self.lyricsCombo.currentText())
        if self.player.now_playing:
            self.findLyrics()

    def findLyrics(self):
        # Stop the previous lyrics thread properly
        if self.lyricsThread is not None:
            self.lyricsThread.quit()
            self.lyricsThread.wait(500)  # Give it time to finish
            self.lyricsThread.deleteLater()
            self.lyricsThread = None

        self.lyricsThread = QThread(self)
        self.lyrics = Lyrics()
        self.lyrics.setConfig(self.config, self.player)
        self.lyrics.moveToThread(self.lyricsThread)

        # Connect signals before starting the thread
        self.lyricsThread.started.connect(self.lyrics.run)
        self.lyrics.finished.connect(lambda text: self.lyricsTxt.setText(text))
        self.lyrics.finished.connect(self.lyrics.deleteLater)
        self.lyricsThread.finished.connect(self.lyricsThread.deleteLater)

        self.lyricsThread.start()

    def next(self):
        nextIndex = self.tableModel.getNextIndex()
        if nextIndex:
            self.play(nextIndex)
            self.selectCurrentTrack()
        else:
            self.stop()

    def prev(self):
        prevIndex = self.tableModel.getPrevIndex()
        if prevIndex:
            self.play(prevIndex)
        else:
            self.stop()

    def nextRnd(self):
        rndIndex = self.tableModel.getRndIndex()
        if rndIndex:
            self.play(rndIndex)
        else:
            self.stop()

    def rescanLibrary(self):
        start_time = time.time()
        self.library.rescan()
        self.treeModel.loadTreeData(self.treeView)
        print(
            "--- Library scan is completed in %s seconds ---"
            % (time.time() - start_time)
        )

    def browseDirClick(self):
        dialog = AddLibraryDirDialog(self)
        dialog.confirmed.connect(self.onDirAdded)
        dialog.exec()

    def onDirAdded(self, directory):
        if directory:
            self.config.addLibraryDir(directory)
            self.library.addDir(directory)
            self.rescanLibrary()
            self.config.save()

    def setPos(self):
        self.timer.stop()
        pos = self.posSlider.value()
        self.player.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def updatePos(self):
        media_pos = int(self.player.mediaplayer.get_position() * 1000)
        self.posSlider.setValue(media_pos)
        if not self.player.mediaplayer.is_playing():
            try:
                self.lastfm.scrobble(
                    self.player.now_playing.artist, self.player.now_playing.title
                )
            except Exception as e:
                print(str(e))
            if self.stopAfterBtn.isChecked():
                self.stopAfterBtn.setChecked(False)
                self.stop()
            else:
                self.nextRnd() if self.rndOrderBtn.isChecked() else self.next()

    def getSelectedIndex(self):
        selectedIndex = self.tableView.selectedIndexes()
        if selectedIndex:
            return selectedIndex[0].row()
        else:
            return None

    def skipTrack(self):
        for index in list(set([i.row() for i in self.tableView.selectedIndexes()])):
            track = self.tableModel.tracks[index]
            if isinstance(track, Track):
                track.skipped = 0 if track.skipped else 1
                track.updateAttr("skipped")
                self.tableModel.tracks[index] = track
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def openSettingsDialog(self):
        dialog = SettingsDialog(self)
        dialog.confirmed.connect(self.saveSettingsFromDialog)
        dialog.geniusToken.setText(self.config.getLyricsGeniusToken())
        dialog.lastFmUsername.setText(self.config.getLastFmUsername())
        dialog.lastFmPassword.setText(self.config.getLastFmPassword())
        dialog.exec()

    def saveSettingsFromDialog(self, values):
        self.config.saveDialogData(json.loads(values))

    def setVolume(self, volume):
        self.player.setVolume(volume)

    def tableModelBeforeChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, 1)

    def tableModelChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, Track.colCount())

    def closeEvent(self, event):
        # Stop lyrics thread before closing
        if self.lyricsThread is not None:
            self.lyricsThread.quit()
            self.lyricsThread.wait(500)
            self.lyricsThread.deleteLater()
            self.lyricsThread = None

        get_sftp_manager().close_all()
        self.config.save()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)

    window = FooQt(app)
    window.setWindowIcon(QIcon("musical-note.png"))
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
