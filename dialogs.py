from PyQt5 import QtWidgets, QtCore
from dialog import Ui_Dialog
import json

class SettingsDialog(QtWidgets.QDialog, Ui_Dialog):
    confirmed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Run the .setupUi() method to show the GUI
        self.setupUi(self)

        self.saveConfigButton.clicked.connect(self.confirm)

    def confirm(self):
        self.close()
        genius_token, lastfm_username, lastfm_password = self.geniusToken.text(), self.lastFmUsername.text(), self.lastFmPassword.text()
        # print('entered values are: %s, %s, %s' % genius_token, lastfm_key, lastfm_secret)
        self.confirmed.emit(json.dumps((genius_token, lastfm_username, lastfm_password)))  # emit the signal, passing the text as its only argument
