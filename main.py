import sys
import os

from PyQt5 import QtWidgets, QtGui, QtCore, QtSql

# from PyQt5.QtCore import Qt, QModelIndex, QDir
# from PyQt5.QtGui import QPalette, QColor, QStandardItemModel, QIcon
# from PyQt5.QtSql import QSqlDatabase, QSqlTableModel
# from PySide2 import QtWidgets, QtGui, QtCore

import design
import config
import library
import player


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)  # Это нужно для инициализации нашего дизайна

        # design updates
        self.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
        self.playBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.nextBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipForward))
        self.prevBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipBackward))
        self.nextRndBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogHelpButton))
        self.browseDirBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOpenButton))
        self.rescanLibBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)

        # config loading
        self.config = config.Config(self, app)
        library.init(self.config.getLibraryDir())

        self.loadTracksToUi()

        self.config.load()

        self.connectEvents()

    def connectEvents(self):
        self.themeCombo.activated.connect(lambda: app.setStyle(self.themeCombo.currentText()))
        self.browseDirBtn.clicked.connect(self.browseDirClick)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.searchEdit.textChanged.connect(self.searchChanged)
        self.treeView.clicked.connect(self.clickTreeView)
        self.tableView.doubleClicked.connect(self.play)
        # self.posSlider.setMaximum(1000)
        self.posSlider.sliderMoved.connect(self.setPos)
        self.posSlider.sliderPressed.connect(self.setPos)
        self.timer.timeout.connect(self.updatePos)

    def loadTracksToUi(self):
        # db and models init
        db = QtSql.QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName('db.sqlite3')
        db.open()

        self.tableModel = QtSql.QSqlTableModel(None, db)
        self.tableModel.setTable('track')
        self.tableModel.select()
        self.tableView.setModel(self.tableModel)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        # self.treeModel = QStandardItemModel()
        self.treeModel = QtWidgets.QFileSystemModel()
        self.treeModel.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)
        self.treeView.setModel(self.treeModel)
        # self.treeView.setRootIndex(self.treeModel.setRootPath(library.root_dir))
        # self.treeModel.setHeaderData()
        # self.treeView.setColumnHidden(2, False)
        # self.treeView.hideColumn(2)
        # self.treeView.setRootIndex(self.treeModel.index(library.root_dir))
        # self.buildTree(library.)
        # self.tableView.currentChanged.connect(self.tableViewChanged)

    def getTrack(self, index: QtCore.QModelIndex):
        track = library.Track()
        track.setAttrs([self.tableModel.data(self.tableModel.index(index.row(), col)) for col in
                        range(0, self.tableModel.columnCount())])
        print(track.__dict__)
        return track

    def play(self, index: QtCore.QModelIndex):
        player.play(self.getTrack(index))
        # index = self.gridModel.index(selInx.row(), library.Track().indexOf('full_path'))


    def tableViewChanged(self, current, previous):
        print(current)


    def clickTreeView(self, index: QtCore.QModelIndex):
        print(index.model().data(index, QtCore.Qt.DisplayRole))
        # self.themeCombo.setCurrentIndex()
        # print(self.themeCombo.findText('cde'))

    def browseDirClick(self):
        # self.themeCombo.setCurrentIndex()
        # print(self.themeCombo.findText('cde'))
        self.config.setLibraryDir(QtWidgets.QFileDialog.getExistingDirectory(self))


    def searchChanged(self):
        self.tableModel.setFilter(f'title LIKE "%{self.searchEdit.text()}%"')

    def playBtnClick(self):
        print([self.tableView.columnWidth(i) for i in range(0, self.tableModel.columnCount())])


    def setPos(self):
        self.timer.stop()
        pos = self.posSlider.value()
        player.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def updatePos(self):
        media_pos = int(player.mediaplayer.get_position() * 1000)
        self.posSlider.setValue(media_pos)

        # No need to call this function if nothing is played
        if not player.mediaplayer.is_playing():
            self.timer.stop()

            # After the video finished, the play button stills shows "Pause",
            if not player.paused:
                player.stop()

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
