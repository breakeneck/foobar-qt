import os
import json
import main
from PyQt5.QtCore import QRect


class Config:
    def __init__(self, widget: main.FooQt, app, filename='config.json'):
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
                'column_sizes': [45, 250, 113, 113, 113, 113, 113, 113, 113, 113, 113],
            }

        app.setStyle(self.config['theme'])

    def load(self):
        print(self.config)
        self.w.themeCombo.setCurrentIndex(self.w.themeCombo.findText(self.config['theme']))
        self.w.setGeometry(QRect(*self.config['window']))
        self.w.splitter.setSizes(self.config['splitter'])
        [self.w.tableView.setColumnWidth(i, width) for i, width in enumerate(self.config['column_sizes'])]
        # print(self.config['column_sizes'])

    # def loadOnUiReady(self):
    #     [self.w.tableView.setColumnWidth(i, width) for i, width in enumerate(self.config['column_sizes'])]

    def save(self):
        self.config['window'] = self.w.geometry().getRect()
        self.config['splitter'] = self.w.splitter.sizes()
        self.config['theme'] = self.w.themeCombo.currentText()
        self.config['column_sizes'] = [self.w.tableView.columnWidth(i) for i in range(0, self.w.tableModel.columnCount())]
        json.dump(self.config, open('config.json', 'w'))

    def setLibraryDir(self, directory):
        self.config['library_dir'] = directory
        self.save()

    def setSelectedDir(self, directory):
        self.config['selected_dir'] = directory
        self.save()

    def getLibraryDir(self):
        return self.config['library_dir']