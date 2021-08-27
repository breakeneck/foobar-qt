import sys
import time

from PyQt5 import QtWidgets, QtCore, Qt, QtGui
from PyQt5.QtWidgets import QShortcut
from PyQt5.Qt import QIcon

import config
import design
import customui
from dialogs import SettingsDialog
from library import Library, Track
from player import Player
from lyrics import Lyrics

import qtawesome as qta

from PyQt5.QtCore import QThread
import keyboard


# class Hotkey(QObject):
#     signal = pyqtSignal()
#
#     def connect(self, event):
#         self.signal.connect(event)
#
#     def listen(self, key):
#         keyboard.add_hotkey(key, self.signal.emit, suppress=True)


# class Hotkeys:
#     def __init__(self, app):
#         self.app = app
#     def map(self, hotkeysMapping):
#         for shortcut, event in hotkeysMapping.items():
#             hotkey = Hotkey(self.app)
#             hotkey.connect(event)
#             hotkey.listen(shortcut)

# class Hotkey(QObject):
#     hotkeys = {}
#
#     def __init__(self, shortcutsMapping):
#         for key, event in shortcutsMapping.items():
#             self.hotkeys[key] = Hotkey()
#
#         for key, event in shortcutsMapping.items():
#             self.hotkeys[key].connect(event)
#             keyboard.add_hotkey(key, self.hotkeys[key].emit, suppress=True)


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)  # Это нужно для инициализации нашего дизайна

        # config loading
        self.config = config.Config(self)
        self.library = Library(self.config.getLibraryDirs())
        self.player = Player()
        self.lyrics = Lyrics()
        self.lyricsThread = QThread(parent=self)

        # make post ui setup after library is initialized
        customui.postSetup(self)

        # Load config goes after postSetupUi() to be able to restore columns width
        self.config.load(app)
        self.connectEvents(app)

        self.tableModel.refreshPlaylist(self.searchEdit.text())
        self.treeModel.loadTreeData(self.treeView)

    def connectEvents(self, app):
        self.themeCombo.activated.connect(lambda: app.setStyle(self.themeCombo.currentText()))
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
        # self.searchEdit.keyPressEvent.connect(self.searchEditKeyPress)
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
        # self.tableModel.endResetModel.connect(self.onTableModelReset)
        # shortcuts
        QShortcut(QtGui.QKeySequence('Ctrl+S'), self).activated.connect(self.skipTrack)
        QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self).activated.connect(self.playBtnClick)
        QShortcut(QtGui.QKeySequence('Ctrl+H'), self).activated.connect(self.showMinimized)
        QShortcut(QtGui.QKeySequence('Ctrl+F'), self).activated.connect(self.goToSearch)

        # self.hotkeys = Hotkeys(self)
        # self.hotkeys.map({
        #     'F1': self.playBtnClick
        # })

    def showEvent(self, a0: QtGui.QShowEvent) -> None:
        self.config.onAppShow()

    def locateCurrentFolder(self):
        if not self.player.now_playing:
            return

        self.treeView.collapseAll()

        parent = self.treeModel.invisibleRootItem()
        for word in self.player.now_playing.getFolder().getRelPath(self.library).split("/"):
            print('searching for word', word)
            for i in range(parent.rowCount()):
                child = parent.child(i)
                if child.text() == word:
                    print(word, child.index())
                    self.treeView.expand(child.index())
                    self.treeView.setCurrentIndex(child.index())
                    parent = child
                    break
        # rootIndex = self.treeModel.index(0, 0)
        # self.treeView.expand(rootIndex)
        # print (self.player.now_playing.getFolder().getRelPath(self.library))
        # if self.treeView.selectedIndexes():
        #     index = self.treeView.selectedIndexes()[0]
        #     self.treeView.scrollTo(index)
            # item = index.model().itemFromIndex(index)
            # print(item.path)
            # print(self.treeModel.getDirPath(index))

    def expandBtnClick(self):
        if self.expandBtn.isChecked():
            # Expand root item
            rootIndex = self.treeModel.index(0, 0)
            self.treeView.expand(rootIndex)
            # Expand all childs of root
            for row in range(self.treeModel.rowCount(rootIndex)):
                index = rootIndex.child(row, 0)
                self.treeView.expand(index)
        else:
            self.treeView.collapseAll()

    def goToSearch(self):
        self.searchEdit.setText('')
        self.searchEdit.setFocus()

    def treeViewClick(self, index: QtCore.QModelIndex):
        self.library.selected_dir_row = index.row()
        self.library.selected_dir = self.treeModel.itemFromIndex(index).dbModel.path  # self.treeModel.getDirPath(index)
        self.config.updateSelectedDir(self.library.selected_dir, self.library.selected_dir_row)
        self.searchChanged()

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Escape:
            self.searchClear()
        pass

    def searchChanged(self):
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def searchClear(self):
        self.searchEdit.setText('')
        self.selectCurrentTrack()
        self.tableView.setFocus()

    def stop(self):
        self.player.stop()
        self.updatePlayStatus()

    def updatePlayStatus(self):
        icon = qta.icon('fa.play') if self.player.isNoMusic() else qta.icon('fa.pause')
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
            print('can\'t move to current index, because its false')

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
            return print('No item selected')

        track = self.player.play(index.row(), self.tableModel.tracks[index.row()])
        if track:
            self.selectCurrentTrack()
            self.updatePlayStatus()
            self.findLyrics()

    def changeLyricsProvider(self, text):
        # self.lyrics.setProvider(self.lyricsCombo.currentText())
        self.config.setLyricsProvider(self.lyricsCombo.currentText())
        self.findLyrics()

    def findLyrics(self):
        if isinstance(self.lyricsThread, QThread):
            self.lyricsThread.quit()
            # self.lyricsThread.wait()
        self.lyricsThread = QThread(parent=self)
        # Step 3: Create a worker object
        self.lyrics = Lyrics()
        self.lyrics.setConfig(self.config, self.player)
        self.lyrics.moveToThread(self.lyricsThread)
        # Step 5: Connect signals and slots
        self.lyricsThread.started.connect(self.lyrics.run)
        self.lyrics.finished.connect(lambda text: self.lyricsTxt.setText(text))
        # self.lyrics.finished.connect(self.lyrics.quit)
        self.lyrics.finished.connect(self.lyrics.deleteLater)
        self.lyricsThread.finished.connect(self.lyricsThread.deleteLater)
        # Step 6: Start the thread
        self.lyricsThread.start()

    def next(self):
        nextIndex = self.tableModel.getNextIndex()
        if nextIndex:
            self.play(nextIndex)
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
        print("--- Library scan is completed in %s seconds ---" % (time.time() - start_time))

    def browseDirClick(self):
        newDir = QtWidgets.QFileDialog.getExistingDirectory(self)
        if newDir:
            self.config.updateLibraryDir(newDir)
            self.library.updateDirs([newDir, '', -1])
            self.rescanLibrary()
            self.config.save()

    def setPos(self):
        self.timer.stop()
        pos = self.posSlider.value()
        self.player.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def updatePos(self):
        media_pos = int(self.player.mediaplayer.get_position() * 1000)
        # print('mediapos', media_pos)
        self.posSlider.setValue(media_pos)
        # No need to call this function if nothing is played
        if not self.player.mediaplayer.is_playing():
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
                track.updateAttr('skipped')
                self.tableModel.tracks[index] = track
        self.tableModel.refreshPlaylist(self.searchEdit.text())
        # QtWidgets.QMessageBox.information(self, 'Message','Track "' + track.getTitle() + '" will be ' + ('skipped ' if track.skipped else 'played'))

    def openSettingsDialog(self):
        dialog = SettingsDialog(self)
        dialog.confirmed.connect(self.saveSettingsFromDialog)
        dialog.geniusToken.setText(self.config.getLyricsGeniusToken())
        dialog.exec()

    def saveSettingsFromDialog(self, token):
        print('token = ' + token)
        self.config.updateLyricsGeniusToken(token)
        self.lyrics.onChangeTokens()

    def setVolume(self, volume):
        self.player.setVolume(volume)

    def tableModelBeforeChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, 1)

    def tableModelChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, Track.colCount())

    def closeEvent(self, event):
        self.config.save()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)  # Новый экземпляр QApplication

    window = FooQt(app)  # Создаём объект класса ExampleApp
    window.setWindowIcon(QIcon('musical-note.png'))
    window.show()  # Показываем окно
    app.exec_()  # и запускаем приложение


if __name__ == '__main__':  # Если мы запускаем файл напрямую, а не импортируем
    main()  # то запускаем функцию main()
