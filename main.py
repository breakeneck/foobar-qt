import sys

from PyQt5 import QtWidgets, QtCore, QtSql
import lyricwikia

import config
import design
import library
import player


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
        self.rescanLibBtn.clicked.connect(library.rescan)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.nextBtn.clicked.connect(self.next)
        self.prevBtn.clicked.connect(self.prev)
        self.nextRndBtn.clicked.connect(self.nextRndBtnClick)
        self.stopAfterChk.clicked.connect(self.stopAfterChkClick)
        self.searchEdit.textChanged.connect(self.searchChanged)
        self.treeView.clicked.connect(self.treeViewClick)
        self.tableView.doubleClicked.connect(self.play)
        self.posSlider.sliderMoved.connect(self.setPos)
        self.posSlider.sliderPressed.connect(self.setPos)
        self.timer.timeout.connect(self.updatePos)
        self.tableModel.modelAboutToBeReset.connect(self.tableModelBeforeChanged)
        self.tableModel.modelReset.connect(self.tableModelChanged)

    def treeViewClick(self, index: QtCore.QModelIndex):
        library.selected_dir = library.TreeModel().getDirPath(index)
        self.searchChanged()

    def searchChanged(self):
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def stop(self):
        self.timer.stop()
        if not player.paused:
            player.stop()
            self.updatePlayIcon()

    def updatePlayIcon(self):
        icon = QtWidgets.QStyle.SP_MediaPause if player.paused else QtWidgets.QStyle.SP_MediaPlay
        self.playBtn.setIcon(self.style().standardIcon(icon))

    def play(self, index: QtCore.QModelIndex = None):
        if not index:
            return print('No item selected')

        track = player.play(index.row(), self.tableModel.tracks[index.row()])

        if track:
            self.timer.start()
            self.updatePlayIcon()
            self.loadLyrics()

    def playBtnClick(self):
        if not player.now_playing:
            return self.play((self.tableView.selectedIndexes() or [None])[0])

        if player.play_pause():
            self.timer.start()
        else:
            self.timer.stop()
        self.updatePlayIcon()

    def next(self):
        print('Playing Next')

        nextIndex = self.tableModel.getNextIndex(player)
        if nextIndex:
            self.play(nextIndex)
            self.tableView.setCurrentIndex(nextIndex)
        else:
            self.stop()

    def prev(self):
        print('Playing Prev')

        prevIndex = self.tableModel.getPrevIndex(player)
        if prevIndex:
            self.play(prevIndex)
            self.tableView.setCurrentIndex(prevIndex)
        else:
            self.stop()

    def nextRndBtnClick(self):
        pass

    def stopAfterChkClick(self):
        player.stop_after = not player.stop_after
        self.stopAfterChk.setChecked(player.stop_after)

    def loadLyrics(self):
        try:
            lyrics = lyricwikia.get_lyrics(player.now_playing.artist, player.now_playing.title)
            self.textBrowser.setText(lyrics)
        except Exception as e:
            print(str(e))
            self.textBrowser.setText('')

    def browseDirClick(self):
        self.config.updateLibraryDir(QtWidgets.QFileDialog.getExistingDirectory(self))
        library.updateDirs(self.config.getLibraryDirs())
        self.treeModel.updateTitle()

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
            if self.stopAfterChk.isChecked():
                self.stopAfterChk.setChecked(False)
                self.stop()
            else:
                self.next()

    def postSetupUi(self):
        # add invisible elements
        self.timer = QtCore.QTimer(self)
        self.treeModel = library.TreeModel()
        self.tableModel = library.TableModel()
        # update qtDesigner non available properties
        self.timer.setInterval(100)
        # design updates
        self.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
        self.playBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.nextBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipForward))
        self.prevBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipBackward))
        self.nextRndBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogHelpButton))
        self.stopAfterChk.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaStop))
        self.browseDirBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOpenButton))
        self.rescanLibBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.posSlider.setMaximum(1000)
        # load Directory tree
        self.treeView.setModel(self.treeModel)
        # load Tracks
        self.tableView.setModel(self.tableModel)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

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
    window.show()  # Показываем окно
    app.exec_()  # и запускаем приложение


if __name__ == '__main__':  # Если мы запускаем файл напрямую, а не импортируем
    main()  # то запускаем функцию main()
