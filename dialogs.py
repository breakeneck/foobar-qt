import json
import os

from PyQt6 import QtCore, QtWidgets

from dialog import Ui_Dialog
from virtualfs import test_connection


class SettingsDialog(QtWidgets.QDialog, Ui_Dialog):
    confirmed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.saveConfigButton.clicked.connect(self.confirm)

    def confirm(self):
        self.close()
        genius_token, lastfm_username, lastfm_password = (
            self.geniusToken.text(),
            self.lastFmUsername.text(),
            self.lastFmPassword.text(),
        )
        self.confirmed.emit(
            json.dumps((genius_token, lastfm_username, lastfm_password))
        )


class AddLibraryDirDialog(QtWidgets.QDialog):
    """Dialog to add either a local directory or an SFTP directory to the library."""

    confirmed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Library Directory")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        # Tab widget for Local / SFTP
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        # --- Local tab ---
        self.local_widget = QtWidgets.QWidget()
        local_layout = QtWidgets.QVBoxLayout(self.local_widget)

        self.local_path_label = QtWidgets.QLabel("Path:")
        local_layout.addWidget(self.local_path_label)

        self.local_path_edit = QtWidgets.QLineEdit()
        local_layout.addWidget(self.local_path_edit)

        self.local_browse_btn = QtWidgets.QPushButton("Browse...")
        self.local_browse_btn.clicked.connect(self._browse_local)
        local_layout.addWidget(self.local_browse_btn)

        self.tabs.addTab(self.local_widget, "Local")

        # --- SFTP tab ---
        self.sftp_widget = QtWidgets.QWidget()
        sftp_layout = QtWidgets.QFormLayout(self.sftp_widget)

        self.sftp_host_label = QtWidgets.QLabel(
            "Host (use SSH config hostname, e.g. 'server')"
        )
        self.sftp_host_edit = QtWidgets.QLineEdit()
        sftp_layout.addRow(self.sftp_host_label, self.sftp_host_edit)

        self.sftp_path_label = QtWidgets.QLabel("Remote path (e.g. /music):")
        self.sftp_path_edit = QtWidgets.QLineEdit()
        sftp_layout.addRow(self.sftp_path_label, self.sftp_path_edit)

        self.sftp_test_btn = QtWidgets.QPushButton("Test connection")
        self.sftp_test_btn.clicked.connect(self._test_sftp)
        sftp_layout.addRow(self.sftp_test_btn)

        self.sftp_status_label = QtWidgets.QLabel()
        self.sftp_status_label.setWordWrap(True)
        sftp_layout.addRow(self.sftp_status_label)

        self.sftp_help_label = QtWidgets.QLabel(
            "Uses your local ~/.ssh/config for authentication.\n"
            "Resulting path: sftp://<host><path>"
        )
        self.sftp_help_label.setWordWrap(True)
        self.sftp_help_label.setStyleSheet("color: gray;")
        sftp_layout.addRow(self.sftp_help_label)

        self.tabs.addTab(self.sftp_widget, "SFTP / SSH")

        # --- Buttons ---
        btn_layout = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.add_button.clicked.connect(self._confirm)
        self.cancel_button.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.cancel_button)
        layout.addLayout(btn_layout)

        self.setMinimumWidth(450)

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        if index == 0:
            self.local_path_edit.setFocus()
        else:
            self.sftp_host_edit.setFocus()

    def _browse_local(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if path:
            self.local_path_edit.setText(path)

    def _get_sftp_url(self):
        host = self.sftp_host_edit.text().strip()
        remote_path = self.sftp_path_edit.text().strip()
        if not remote_path.startswith("/"):
            remote_path = "/" + remote_path
        return "sftp://{}{}".format(host, remote_path)

    def _test_sftp(self):
        host = self.sftp_host_edit.text().strip()
        if not host:
            self.sftp_status_label.setText("Please enter a hostname first.")
            self.sftp_status_label.setStyleSheet("color: red;")
            return

        self.sftp_status_label.setText("Testing connection...")
        self.sftp_status_label.setStyleSheet("color: gray;")
        self.sftp_test_btn.setEnabled(False)

        sftp_url = self._get_sftp_url()

        ok, msg = test_connection(sftp_url)
        if ok:
            self.sftp_status_label.setText(msg)
            self.sftp_status_label.setStyleSheet("color: green;")
        else:
            self.sftp_status_label.setText("Failed: %s" % msg)
            self.sftp_status_label.setStyleSheet("color: red;")

        self.sftp_test_btn.setEnabled(True)

    def _confirm(self):
        current_tab = self.tabs.currentIndex()

        if current_tab == 0:
            path = self.local_path_edit.text().strip()
            if not path:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Please enter a local path or click Browse."
                )
                return
            expanded = os.path.expanduser(path)
            if not os.path.isdir(expanded):
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Directory does not exist:\n{}".format(expanded)
                )
                return
            self.confirmed.emit(expanded)
            self.accept()

        elif current_tab == 1:
            host = self.sftp_host_edit.text().strip()
            remote_path = self.sftp_path_edit.text().strip()

            if not host:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Error",
                    "Please enter a hostname (as defined in ~/.ssh/config).",
                )
                return
            if not remote_path:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Please enter a remote path."
                )
                return
            if not remote_path.startswith("/"):
                remote_path = "/" + remote_path

            sftp_url = "sftp://{}{}".format(host, remote_path)

            ok, msg = test_connection(sftp_url)
            if not ok:
                QtWidgets.QMessageBox.warning(
                    self,
                    "SFTP Error",
                    "Could not access the remote path.\n\n%s" % msg,
                )
                return

            self.confirmed.emit(sftp_url)
            self.accept()
