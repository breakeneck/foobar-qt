import sys  # sys нужен для передачи argv в QApplication
import os
from PyQt5.QtCore import Qt
from PyQt5 import QtWidgets
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import QDir
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtSql import QSqlDatabase, QSqlTableModel
from PyQt5.QtGui import QStandardItemModel
# from PyQt5.QtGui import QIcon
# from PyQt5.QtCore import
from PyQt5.QtWidgets import QAbstractItemView

import design  # Это наш конвертированный файл дизайна
import config
import library


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        # Это здесь нужно для доступа к переменным, методам
        # и т.д. в файле design.py
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

        # config loading
        self.config = config.Config(self, app)
        library.init(self.config.getLibraryDir())

        # db and models init
        db = QSqlDatabase.addDatabase('QSQLITE')
        db.setDatabaseName('db.sqlite3')
        db.open()

        self.gridModel = QSqlTableModel(None, db)
        self.gridModel.setTable('track')
        self.gridModel.select()
        self.tableView.setModel(self.gridModel)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        # self.treeModel = QStandardItemModel()
        self.treeModel = QtWidgets.QFileSystemModel()
        self.treeModel.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self.treeView.setModel(self.treeModel)
        # self.treeView.setRootIndex(self.treeModel.setRootPath(library.root_dir))
        # self.treeModel.setHeaderData()
        # self.treeView.setColumnHidden(2, False)
        # self.treeView.hideColumn(2)
        # self.treeView.setRootIndex(self.treeModel.index(library.root_dir))
        # self.buildTree(library.)

        self.themeCombo.activated.connect(lambda: app.setStyle(self.themeCombo.currentText()))
        self.browseDirBtn.clicked.connect(self.browseDirClick)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.searchEdit.textChanged.connect(self.searchChanged)
        self.treeView.clicked.connect(self.clickTreeView)
        # self.tableView.columnc()

        # self.tableView.currentChanged.connect(self.tableViewChanged)

        self.config.load()

    def tableViewChanged(self, current, previous):
        print(current)


    def clickTreeView(self, index: QModelIndex):
        print(index.model().data(index, Qt.DisplayRole))
        # self.themeCombo.setCurrentIndex()
        # print(self.themeCombo.findText('cde'))

    def browseDirClick(self):
        # self.themeCombo.setCurrentIndex()
        # print(self.themeCombo.findText('cde'))
        self.config.setLibraryDir(QtWidgets.QFileDialog.getExistingDirectory(self))


    def searchChanged(self):
        self.gridModel.setFilter(f'title LIKE "%{self.searchEdit.text()}%"')

    def playBtnClick(self):
        print([self.tableView.columnWidth(i) for i in range(0, self.gridModel.columnCount())])
            # print(self.tableView.columnWidth(i))

        # print(self.geometry())
        # self.setGeometry(QRect(*self.config['window']))



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
