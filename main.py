import sys

from PyQt5 import QtWidgets, QtCore, QtSql

import config
import design
import library
import player


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self):
        super(TableModel, self).__init__()
        self.headers = ["Scientist name", "Birthdate", "Contribution"]
        self.rows = [("Newton", "1643-01-04", "Classical mechanics"),
                ("Einstein", "1879-03-14", "Relativity"),
                ("Darwin", "1809-02-12", "Evolution")]

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=None):
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        return self.rows[index.row()][index.column()]

    def headerData(self, section, orientation, role=None):
        if role != QtCore.Qt.DisplayRole or orientation != QtCore.Qt.Horizontal:
            return QtCore.QVariant()
        return self.headers[section]


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)  # Это нужно для инициализации нашего дизайна

        # config loading
        self.config = config.Config(self)
        library.init(self.config.getLibraryDirs())

        # make post ui setup after library is initialized
        self.postSetupUi()

        # Load config goes after loadTracksToUi() to be able to restore columns width
        self.config.load(app)
        self.connectEvents(app)

    def connectEvents(self, app):
        self.themeCombo.activated.connect(lambda: app.setStyle(self.themeCombo.currentText()))
        self.browseDirBtn.clicked.connect(self.browseDirClick)
        self.rescanLibBtn.clicked.connect(library.rescan)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.searchEdit.textChanged.connect(self.searchChanged)
        self.treeView.clicked.connect(self.treeViewClick)
        self.tableView.doubleClicked.connect(self.play)
        # self.posSlider.setMaximum(1000)
        self.posSlider.sliderMoved.connect(self.setPos)
        self.posSlider.sliderPressed.connect(self.setPos)
        self.timer.timeout.connect(self.updatePos)

    def treeViewClick(self, index: QtCore.QModelIndex):
        library.selected_dir = library.TreeModel().getDirPath(index)
        self.searchChanged()
        print(library.selected_dir)

    def getTrack(self, index: QtCore.QModelIndex):
        track = library.Track()
        track.setAttrs([self.tableModel.data(self.tableModel.index(index.row(), col)) for col in
                        range(0, self.tableModel.columnCount())])
        print(track.__dict__)
        return track

    def play(self, index: QtCore.QModelIndex):
        player.play(self.getTrack(index))
        # index = self.gridModel.index(selInx.row(), library.Track().indexOf('full_path'))


    def browseDirClick(self):
        # self.themeCombo.setCurrentIndex()
        # print(self.themeCombo.findText('cde'))
        self.config.updateLibraryDir(QtWidgets.QFileDialog.getExistingDirectory(self))


    def searchChanged(self):
        query = ''
        if self.searchEdit.text():
            query = f'(title LIKE "%{self.searchEdit.text()}%" OR artist LIKE "%{self.searchEdit.text()}%")'

        if library.selected_dir:
            if query:
                query += ' AND '
            query += f'(dir_name LIKE "{library.selected_dir}%")'

        print(query)
        self.tableModel.setFilter(query)

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

    def postSetupUi(self):
        # add invisible elements
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        # design updates
        self.themeCombo.addItems(QtWidgets.QStyleFactory.keys())
        self.playBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.nextBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipForward))
        self.prevBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipBackward))
        self.nextRndBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogHelpButton))
        self.browseDirBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOpenButton))
        self.rescanLibBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        # load Directory tree
        self.treeModel = library.TreeModel()
        self.treeModel.loadTreeData()
        self.treeView.setModel(self.treeModel)
        #load Tracks
        db = QtSql.QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName('db.sqlite3')
        db.open()

        self.tableModel = QtSql.QSqlTableModel(None, db)
        self.tableModel.setTable('track')
        self.tableModel.select()
        self.tableView.setModel(self.tableModel)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)


def main():
    app = QtWidgets.QApplication(sys.argv)  # Новый экземпляр QApplication

    window = FooQt(app)  # Создаём объект класса ExampleApp
    window.show()  # Показываем окно
    app.exec_()  # и запускаем приложение


if __name__ == '__main__':  # Если мы запускаем файл напрямую, а не импортируем
    main()  # то запускаем функцию main()
