from PyQt5 import QtWidgets, QtCore
from dialog import Ui_Dialog


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