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
                'volume': 100,
                'lyrics_genius_token': '',
                'lyrics_provider': ''
            }

    def load(self, app: QApplication):
        # print(self.config)
        app.setStyle(self.config['theme'])
        self.w.themeCombo.setCurrentIndex(self.w.themeCombo.findText(self.config['theme']))
        self.w.lyricsCombo.setCurrentIndex(self.w.lyricsCombo.findText(self.config['lyrics_provider']))
        self.w.setGeometry(QRect(*self.config['window']))
        self.w.splitter.setSizes(self.config['splitter'])
        self.w.rndOrderBtn.setChecked(self.config['rndOrder'])
        [self.w.tableView.setColumnWidth(i, width) for i, width in enumerate(self.config['column_sizes'])]
        self.w.volumeSlider.setValue(self.config['volume'])
        self.w.setVolume(self.w.volumeSlider.value())
        self.w.searchEdit.setText(self.config['search'])

    def onAppShow(self):
        self.w.treeView.verticalScrollBar().setSliderPosition(self.config['treeview_scroll_pos'])
        self.w.tableView.verticalScrollBar().setSliderPosition(self.config['tableview_scroll_pos'])

        rootTreeItem = self.w.treeModel.invisibleRootItem()
        for item in self.w.treeModel.iterItems(rootTreeItem):
            if item.dbModel.path == self.config['treeview_path']:
                self.w.treeView.setCurrentIndex(item.index())
                break

    def save(self):
        self.config['window'] = self.w.geometry().getRect()
        self.config['splitter'] = self.w.splitter.sizes()
        self.config['rndOrder'] = self.w.rndOrderBtn.isChecked()
        self.config['theme'] = self.w.themeCombo.currentText()
        self.config['lyrics_provider'] = self.w.lyricsCombo.currentText()
        self.config['column_sizes'] = [self.w.tableView.columnWidth(i) for i in range(0, self.w.tableModel.columnCount())]
        self.config['volume'] = self.w.volumeSlider.value()
        self.config['search'] = self.w.searchEdit.text()
        if self.w.treeView.selectedIndexes():
            index = self.w.treeView.selectedIndexes()[0]
            item = index.model().itemFromIndex(index)
            self.config['treeview_path'] = item.dbModel.path
        self.config['treeview_scroll_pos'] = self.w.treeView.verticalScrollBar().value()
        self.config['tableview_scroll_pos'] = self.w.tableView.verticalScrollBar().value()
        json.dump(self.config, open('config.json', 'w'))

        rootTreeItem = self.w.treeModel.invisibleRootItem()
        for item in self.w.treeModel.iterItems(rootTreeItem):
            if int(self.w.treeView.isExpanded(item.index())) != item.dbModel.is_expanded:
                item.dbModel.is_expanded = int(self.w.treeView.isExpanded(item.index()))
                item.dbModel.update()

    def getTreeViewItem(self):
        return self.config['treeview_path']

    def updateLibraryDir(self, directory):
        self.config['library_dir'] = directory
        # self.save()

    def updateSelectedDir(self, directory, row):
        self.config['selected_dir'] = directory
        self.config['selected_dir_row'] = row
        # self.save()

    def getLibraryDirs(self):
        return self.config['library_dir'], self.config['selected_dir'], self.config['selected_dir_row']

    def getLyricsGeniusToken(self):
        return self.config['lyrics_genius_token'] if 'lyrics_genius_token' in self.config else ''

    def updateLyricsGeniusToken(self, token):
        self.config['lyrics_genius_token'] = token
        self.save()

    def getLyricsProvider(self):
        return self.config['lyrics_provider']