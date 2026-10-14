import json
import os

from PyQt6 import QtCore, QtGui, QtWidgets

import hotkeys
from dialog import Ui_Dialog
from virtualfs import test_connection


class SettingsDialog(QtWidgets.QDialog, Ui_Dialog):
    confirmed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.saveConfigButton.clicked.connect(self.confirm)

        # audio buffer slider: 1.0-3.0 s in 0.1 s steps (value is in 100 ms)
        self.audioCachingSlider.setRange(10, 30)
        self.audioCachingSlider.setSingleStep(1)
        self.audioCachingSlider.setPageStep(5)
        self.audioCachingSlider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBothSides)
        self.audioCachingSlider.setTickInterval(5)
        self.audioCachingSlider.setValue(30)
        self.audioCachingSlider.valueChanged.connect(self._cachingChanged)

        # stop-after-current behaviour (the .ui uses absolute geometry,
        # so new widgets are placed below the audio slider)
        self.stopAfterLabel = QtWidgets.QLabel(
            "When 'Stop after current' triggers:", self
        )
        self.stopAfterLabel.setGeometry(QtCore.QRect(10, 330, 431, 22))
        self.stopAfterCombo = QtWidgets.QComboBox(self)
        self.stopAfterCombo.setGeometry(QtCore.QRect(10, 355, 431, 31))
        self.stopAfterCombo.addItems(
            [
                "Uncheck the button (stop once per activation)",
                "Keep the button checked (stop after every played track)",
            ]
        )
        self.hotkeysBtn = QtWidgets.QPushButton("Keyboard shortcuts...", self)
        self.hotkeysBtn.setGeometry(QtCore.QRect(10, 400, 200, 38))
        self.hotkeysBtn.clicked.connect(self.openHotkeysDialog)
        self.saveConfigButton.setGeometry(QtCore.QRect(330, 400, 107, 38))
        self.resize(459, 450)

    def openHotkeysDialog(self):
        # parent() is the FooQt window (SettingsDialog is built with it)
        window = self.parent()
        if window is None or not hasattr(window, "hotkeys"):
            return
        HotkeysDialog(window, self).exec()

    def setStopAfterMode(self, mode):
        self.stopAfterCombo.setCurrentIndex(0 if mode == "auto" else 1)

    def getStopAfterMode(self):
        return "auto" if self.stopAfterCombo.currentIndex() == 0 else "persistent"

    def _cachingChanged(self, value):
        self.audioCachingValue.setText(f"{value / 10:.1f} s")

    def setAudioCachingMs(self, ms):
        self.audioCachingSlider.setValue(int(ms) // 100)

    def getAudioCachingMs(self):
        return self.audioCachingSlider.value() * 100

    def confirm(self):
        self.close()
        values = (
            self.geniusToken.text(),
            self.lastFmUsername.text(),
            self.lastFmPassword.text(),
            self.getAudioCachingMs(),
            self.getStopAfterMode(),
        )
        self.confirmed.emit(json.dumps(values))


class HotkeysDialog(QtWidgets.QDialog):
    """Maps FooQt actions to in-app and (on KDE) global shortcuts."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.fooqtWindow = window
        self.setWindowTitle("Keyboard shortcuts")
        self.setModal(True)

        layout = QtWidgets.QGridLayout(self)
        self.localEdits = {}
        self.globalEdits = {}

        self.globalSupported = window.hotkeys.globalAccel.available()

        for column, title in enumerate(("Action", "In-app shortcut", "Global shortcut")):
            header = QtWidgets.QLabel("<b>%s</b>" % title)
            layout.addWidget(header, 0, column)

        mapping = window.config.getHotkeys()
        row = 1
        for action_id, label, _default in hotkeys.ACTIONS:
            layout.addWidget(QtWidgets.QLabel(label), row, 0)

            local = QtWidgets.QKeySequenceEdit(self)
            local.setKeySequence(QtGui.QKeySequence(mapping[action_id]["local"]))
            layout.addWidget(local, row, 1)
            self.localEdits[action_id] = local

            global_edit = QtWidgets.QKeySequenceEdit(self)
            global_edit.setKeySequence(QtGui.QKeySequence(mapping[action_id]["global"]))
            global_edit.setEnabled(self.globalSupported)
            layout.addWidget(global_edit, row, 2)
            self.globalEdits[action_id] = global_edit
            row += 1

        if self.globalSupported:
            note_text = (
                "Global shortcuts are registered with KDE (KWin). Prefer a "
                "modifier combo (e.g. Ctrl+Alt+P) or a media key (Play, Next). "
                "QKeySequenceEdit cannot capture bare Escape, but Escape stays "
                "the Minimize default (it clears the search first when the "
                "search field holds text)."
            )
        else:
            note_text = (
                "Global shortcuts require a KDE (KWin) session with the gdbus "
                "tool; unavailable here, so only in-app shortcuts apply."
            )
        note = QtWidgets.QLabel(note_text)
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note, row, 0, 1, 3)
        row += 1

        buttons = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save")
        save.clicked.connect(self._save)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        layout.addLayout(buttons, row, 0, 1, 3)

        self.setMinimumWidth(560)

    def _save(self):
        mapping = {}
        for action_id, _label, _default in hotkeys.ACTIONS:
            mapping[action_id] = {
                "local": self.localEdits[action_id].keySequence().toString(),
                "global": self.globalEdits[action_id].keySequence().toString(),
            }
        report = self.fooqtWindow.applyHotkeys(mapping)
        if report:
            QtWidgets.QMessageBox.warning(
                self,
                "Global shortcuts",
                "Could not register some global shortcuts:\n"
                + "\n".join("%s (%s): %s" % entry for entry in report),
            )
        self.accept()


class AddLibraryDirDialog(QtWidgets.QDialog):
    """Dialog to add either a local directory or an SFTP directory to the library."""

    confirmed = QtCore.pyqtSignal(str)
    formSaved = QtCore.pyqtSignal(str)

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

    def setInitialForm(self, data):
        """Restore the previously entered values."""
        self.local_path_edit.setText(data.get("local", ""))
        self.sftp_host_edit.setText(data.get("sftp_host", ""))
        self.sftp_path_edit.setText(data.get("sftp_path", ""))
        self.tabs.setCurrentIndex(data.get("tab", 0))

    def _form_data(self):
        return json.dumps(
            {
                "local": self.local_path_edit.text().strip(),
                "sftp_host": self.sftp_host_edit.text().strip(),
                "sftp_path": self.sftp_path_edit.text().strip(),
                "tab": self.tabs.currentIndex(),
            }
        )

    def _on_tab_changed(self, index):
        if index == 0:
            self.local_path_edit.setFocus()
        else:
            self.sftp_host_edit.setFocus()

    def reject(self):
        # keep whatever the user typed even when the dialog is cancelled
        self.formSaved.emit(self._form_data())
        super().reject()

    def closeEvent(self, event):
        self.formSaved.emit(self._form_data())
        super().closeEvent(event)

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
            self.local_path_edit.setText(expanded)
            self.formSaved.emit(self._form_data())
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

            self.sftp_path_edit.setText(remote_path)
            self.formSaved.emit(self._form_data())
            self.confirmed.emit(sftp_url)
            self.accept()
