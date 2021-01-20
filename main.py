import sys
import time

from PyQt5 import QtWidgets, QtCore, Qt
import qtawesome as qta

import config
import design
import library
import player
from lyrics import Lyrics
from pyqt_custom import SettingsDialog


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)

        self.config = config.Config(self)
        library.init(self.config.getLibraryDirs())
        self.lyrics = Lyrics(self.config)

        # run postSetupUI after library is initialized (Why??)
        from main_ui_setup import MainUiSetup
        mainUiSetup = MainUiSetup()
        mainUiSetup.tune(self)
        mainUiSetup.connectEvents(self, app)
        mainUiSetup.loadUiState(self, app)
        mainUiSetup.initPlaylist(self)

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
        icon = qta.icon('fa.play') if player.isNoMusic() else qta.icon('fa.pause')
        self.playBtn.setIcon(icon)
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
            self.lyricsTxt.setText(self.lyrics.find())

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


    def setPos(self):
        self.timer.stop()
        pos = self.posSlider.value()
        player.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def updatePos(self):
        media_pos = int(player.mediaplayer.get_position() * 1000)
        self.posSlider.setValue(media_pos)
        if not player.mediaplayer.is_playing():
            if self.stopAfterBtn.isChecked():
                self.stopAfterBtn.setChecked(False)
                self.stop()
            else:
                self.nextRnd() if self.rndOrderBtn.isChecked() else self.next()

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
