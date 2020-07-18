import os
import json
import main
from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication


class Config:
    def __init__(self, widget: main.FooQt, filename='config.json'):
        self.w = widget
        self.filename = filename

        if os.path.isfile(filename):
            self.config = json.load(open(filename))
        else:
            self.config = {
                'theme': 'cde',
                'window': [233, 181, 1067, 631],
                'splitter': [246, 519, 276],
                'library_dir': '~/Music',
                'selected_dir': '',
                'selected_dir_row': -1,
                'column_sizes': [45, 250, 113, 113, 113, 113, 113, 113, 113, 113, 113],
            }

    def load(self, app: QApplication):
        print(self.config)
        app.setStyle(self.config['theme'])
        self.w.themeCombo.setCurrentIndex(self.w.themeCombo.findText(self.config['theme']))
        self.w.setGeometry(QRect(*self.config['window']))
        self.w.splitter.setSizes(self.config['splitter'])
        self.w.rndOrderBtn.setChecked(self.config['rndOrder'])
        [self.w.tableView.setColumnWidth(i, width) for i, width in enumerate(self.config['column_sizes'])]

    def save(self):
        self.config['window'] = self.w.geometry().getRect()
        self.config['splitter'] = self.w.splitter.sizes()
        self.config['rndOrder'] = self.w.rndOrderBtn.isChecked()
        self.config['theme'] = self.w.themeCombo.currentText()
        self.config['column_sizes'] = [self.w.tableView.columnWidth(i) for i in range(0, self.w.tableModel.columnCount())]
        json.dump(self.config, open('config.json', 'w'))

    def updateLibraryDir(self, directory):
        self.config['library_dir'] = directory
        # self.save()

    def updateSelectedDir(self, directory, row):
        self.config['selected_dir'] = directory
        self.config['selected_dir_row'] = row
        # self.save()

    def getLibraryDirs(self):
        return self.config['library_dir'], self.config['selected_dir'], self.config['selected_dir_row']