import sys
import time

from PyQt5 import QtWidgets, QtCore, QtSql, Qt
import lyricwikia
# from PyLyrics import *
import lyricsgenius

import config
import design
import library
import player
from dialog import Ui_Dialog
import qtawesome as qta


class StatusBar(QtWidgets.QStatusBar):
    clicked = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()


class SettingsDialog(QtWidgets.QDialog, Ui_Dialog):
    confirmed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Run the .setupUi() method to show the GUI
        self.setupUi(self)

        self.saveConfigButton.clicked.connect(self.confirm)


    def confirm(self):
        self.close()
        value = self.geniusToken.text()
        print('entered value: %s' % value)
        self.confirmed.emit(value)  # emit the signal, passing the text as its only argument


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)  # Это нужно для инициализации нашего дизайна

        # config loading
        self.config = config.Config(self)
        library.init(self.config.getLibraryDirs())

        # make post ui setup after library is initialized
        self.postSetupUi()

        # Load config goes after postSetupUi() to be able to restore columns width
        self.config.load(app)
        self.connectEvents(app)

        self.tableModel.refreshPlaylist()

    def connectEvents(self, app):
        self.themeCombo.activated.connect(lambda: app.setStyle(self.themeCombo.currentText()))
        self.browseDirBtn.clicked.connect(self.browseDirClick)
        self.rescanLibBtn.clicked.connect(self.rescanLibrary)
        self.settingsBtn.clicked.connect(self.openSettingsDialog)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.nextBtn.clicked.connect(self.next)
        self.prevBtn.clicked.connect(self.prev)
        self.nextRndBtn.clicked.connect(self.nextRnd)
        self.searchEdit.textChanged.connect(self.searchChanged)
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

    def treeViewClick(self, index: QtCore.QModelIndex):
        library.selected_dir_row = index.row()
        library.selected_dir = library.TreeModel().getDirPath(index)
        self.config.updateSelectedDir(library.selected_dir, library.selected_dir_row)
        self.searchChanged()

    def searchChanged(self):
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def stop(self):
        player.stop()
        self.updatePlayStatus()

    def updatePlayStatus(self):
        icon = QtWidgets.QStyle.SP_MediaPlay if player.isNoMusic() else QtWidgets.QStyle.SP_MediaPause
        self.playBtn.setIcon(self.style().standardIcon(icon))
        if player.isNoMusic():
            self.timer.stop()
        else:
            self.timer.start()
        self.statusbar.showMessage(player.getNowPlayingMsg())

    def selectCurrentTrack(self):
        currentIndex = self.tableModel.getNowPlayIndex()
        if currentIndex is not False:
            self.tableView.setCurrentIndex(currentIndex)

    def playBtnClick(self):
        if not player.now_playing:
            return self.play((self.tableView.selectedIndexes() or [None])[0])

        player.playPause()
        self.updatePlayStatus()

    def play(self, index: QtCore.QModelIndex = None):
        if not index:
            return print('No item selected')

        track = player.play(index.row(), self.tableModel.tracks[index.row()])
        if track:
            self.selectCurrentTrack()
            self.updatePlayStatus()
            self.loadLyrics()

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


    def loadLyrics(self):
        try:
            # lyrics = lyricwikia.get_lyrics(player.now_playing.artist, player.now_playing.title)
            # lyrics = PyLyrics.getLyrics(player.now_playing.artist, player.now_playing.title)
            song = self.genius.search_song(player.now_playing.title, player.now_playing.artist)
            self.textBrowser.setText(song.lyrics)
        except Exception as e:
            print(str(e))
            self.textBrowser.setText(player.now_playing.artist + ': ' + player.now_playing.title
                                     + '\nLyrics server error: ' + str(e))

    def rescanLibrary(self):
        start_time = time.time()
        library.rescan()
        self.treeModel.loadTreeData()
        print("--- Library scan is completed in %s seconds ---" % (time.time() - start_time))


    def browseDirClick(self):
        newDir = QtWidgets.QFileDialog.getExistingDirectory(self)
        if newDir:
            self.config.updateLibraryDir(newDir)
            library.updateDirs([newDir, '', -1])
            self.rescanLibrary()

    def expandBtnClick(self):
        print(self.expandBtn.isChecked())
        # self.treeModel.
        # self.treeView.rootIndex().child()


    def setPos(self):
        self.timer.stop()
        pos = self.posSlider.value()
        player.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def updatePos(self):
        media_pos = int(player.mediaplayer.get_position() * 1000)
        # print('mediapos', media_pos)
        self.posSlider.setValue(media_pos)
        # No need to call this function if nothing is played
        if not player.mediaplayer.is_playing():
            if self.stopAfterBtn.isChecked():
                self.stopAfterBtn.setChecked(False)
                self.stop()
            else:
                self.nextRnd() if self.rndOrderBtn.isChecked() else self.next()

    def postSetupUi(self):
        # add invisible elements
        self.timer = QtCore.QTimer(self)
        self.treeModel = library.TreeModel()
        self.tableModel = library.TableModel()
        self.statusbar = StatusBar()
        # update qtDesigner non available properties
        self.timer.setInterval(100)
        # design updates
        self.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
        self.playBtn.setIcon(qta.icon('fa.play'))
        self.nextBtn.setIcon(qta.icon('mdi.skip-next'))
        self.prevBtn.setIcon(qta.icon('mdi.skip-previous'))
        self.nextRndBtn.setIcon(qta.icon('fa.question'))
        self.stopAfterBtn.setIcon(qta.icon('fa.stop-circle'))
        self.rndOrderBtn.setIcon(qta.icon('fa.random'))
        self.browseDirBtn.setIcon(qta.icon('fa.folder-open'))
        self.rescanLibBtn.setIcon(qta.icon('mdi.refresh'))
        self.expandBtn.setIcon(qta.icon('mdi.arrow-expand-vertical'))
        self.settingsBtn.setIcon(qta.icon('fa.cog'))

        self.posSlider.setMaximum(1000)
        # load Directory tree
        self.treeView.setModel(self.treeModel)
        # load Tracks
        self.tableView.setModel(self.tableModel)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # my custom statusbar
        self.statusbar.setObjectName("statusbar")
        self.setStatusBar(self.statusbar)
        # statusbar widgets
        self.volumeSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.volumeSlider.setMaximum(100)
        self.volumeSlider.setValue(player.getVolume())
        self.volumeSlider.setToolTip("Volume")
        self.volumeSlider.setFixedWidth(100)
        self.statusbar.addPermanentWidget(self.volumeSlider)
        # Load Lyrics settings
        self.genius = lyricsgenius.Genius(self.config.getLyricsGeniusToken())

    def openSettingsDialog(self):
        dialog = SettingsDialog(self)
        dialog.confirmed.connect(self.saveSettingsFromDialog)
        dialog.exec()
        # dialog = QtWidgets.QDialog()
        # dialog.ui = SettingsDialogUi()
        # dialog.ui.setupUi(dialog)
        # dialog.confirmed.connect(self.saveSettingsDialog)
        # dialog.exec_()
        # dialog.show()

    def saveSettingsFromDialog(self, token):
        print('token = ' + token)
        self.config.updateLyricsGeniusToken(token)

    def setVolume(self, volume):
        player.setVolume(volume)

    def tableModelBeforeChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, 1)

    def tableModelChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, library.Track.colCount())

    def closeEvent(self, event):
        self.config.save()
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)  # Новый экземпляр QApplication

    window = FooQt(app)  # Создаём объект класса ExampleApp
    window.setWindowIcon(Qt.QIcon('musical-note.png'))
    window.show()  # Показываем окно
    app.exec_()  # и запускаем приложение


if __name__ == '__main__':  # Если мы запускаем файл напрямую, а не импортируем
    main()  # то запускаем функцию main()
