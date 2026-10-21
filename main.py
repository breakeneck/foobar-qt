import json
import sys
import time

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QThread

import appicon
import config
import customui
import design
import hotkeys
import remote
from dialogs import AddLibraryDirDialog, SettingsDialog
from virtualfs import get_root_label, is_sftp_path
from lastfm import LastFM
from library import Library, Scanner, Track
from lyrics import Lyrics
from player import Player
from sftp import get_sftp_manager


class FooQt(QtWidgets.QMainWindow, design.Ui_MainWindow):
    def __init__(self, app):
        super().__init__()
        self.setupUi(self)

        # config loading
        self.config = config.Config(self)
        self.library = Library(self.config.getLibraryDirs())
        self.player = Player()
        self.player.network_caching_ms = self.config.getAudioCachingMs()
        # (QThread, Lyrics) pairs kept referenced until they finish
        self._lyricsWorkers = []
        self._lyricsRequest = 0
        self.lastfm = LastFM(self.config)

        # make post ui setup after library is initialized
        customui.postSetup(self)

        # Load config goes after postSetupUi() to be able to restore columns width
        self.config.load(app)
        self.connectEvents(app)

        # keyboard control: remappable in-app shortcuts + KDE global hotkeys
        self.hotkeys = hotkeys.HotkeyManager(self)
        report = self.hotkeys.apply(self.config.getHotkeys())
        if report:
            self.statusbar.showMessage(
                "Global shortcut failed: %s" % report[0][2], 5000
            )

        self.tableModel.refreshPlaylist(self.searchEdit.text())
        self.treeModel.loadTreeData(self.treeView)

        # Zed-style: check/install the remote scan agent on every configured
        # SFTP host right away, in the background.
        remote.ensure_agents_async(self.library.getAllRootDirs())

    def connectEvents(self, app):
        self.themeCombo.activated.connect(self.themeChanged)
        self.lyricsCombo.activated.connect(self.changeLyricsProvider)
        self.browseDirBtn.clicked.connect(self.browseDirClick)
        self.rescanLibBtn.clicked.connect(self.rescanLibrary)
        self.settingsBtn.clicked.connect(self.openSettingsDialog)
        self.playBtn.clicked.connect(self.playBtnClick)
        self.nextBtn.clicked.connect(self.next)
        self.prevBtn.clicked.connect(self.prev)
        self.nextRndBtn.clicked.connect(self.nextRnd)
        self.searchEdit.textChanged.connect(self.searchChanged)
        self.searchEdit.returnPressed.connect(self.stopAndPlay)
        self.searchClearBtn.clicked.connect(self.searchClear)
        # currentChanged (not clicked) also fires on arrow-key navigation
        self.treeView.selectionModel().currentChanged.connect(self.treeViewClick)
        self.tableView.doubleClicked.connect(self.play)
        self.posSlider.sliderMoved.connect(self.setPos)
        self.posSlider.sliderPressed.connect(self.setPos)
        self.timer.timeout.connect(self.updatePos)
        self.tableModel.modelAboutToBeReset.connect(self.tableModelBeforeChanged)
        self.tableModel.modelReset.connect(self.tableModelChanged)
        self.statusbar.clicked.connect(self.selectCurrentTrack)
        self.expandBtn.clicked.connect(self.expandBtnClick)
        self.volumeSlider.valueChanged.connect(self.setVolume)
        self.followTreeView.clicked.connect(self.locateCurrentFolder)
        # media library management lives in the tree's context menu
        self.treeView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self.treeContextMenu)

    def themeChanged(self):
        QtWidgets.QApplication.instance().setStyle(self.themeCombo.currentText())
        # glyphs were rendered with the old palette color -> re-render them
        customui.rethemeIcons(self)

    def changeEvent(self, event: QtCore.QEvent):
        super().changeEvent(event)
        # KDE/system color scheme switched while running: Qt propagates the
        # new palette to this window, but the pre-rendered glyphs must be
        # re-rendered with the new text color
        if event.type() == QtCore.QEvent.Type.PaletteChange:
            customui.rethemeIcons(self)

    def showEvent(self, a0: QtGui.QShowEvent) -> None:
        self.config.onAppShow()

    def locateCurrentFolder(self):
        if not self.player.now_playing:
            return

        self.treeView.collapseAll()

        # Match the track's dir_name against node paths (works for the full
        # hierarchy under each root).
        dir_name = self.player.now_playing.dir_name

        root_item = None
        target_item = None
        for i in range(self.treeModel.rowCount()):
            item = self.treeModel.item(i, 0)
            root = item.dbModel.path
            if dir_name == root:
                # The track lives directly in the root folder
                root_item = target_item = item
                break
            if dir_name.startswith(root + "/"):
                for node in self.treeModel.iterItems(item):
                    if node.dbModel.path == dir_name:
                        root_item, target_item = item, node
                        break
                if target_item is not None:
                    break

        if root_item is None or target_item is None:
            return

        # Expand the whole chain from the root down to the target folder
        chain = []
        node = target_item
        while node is not None:
            chain.append(node)
            if node is root_item:
                break
            node = node.parent()
        for node in reversed(chain):
            self.treeView.expand(node.index())

        self.treeView.setCurrentIndex(target_item.index())
        self.treeViewClick(target_item.index())
        self.selectCurrentTrack()

    def expandBtnClick(self):
        if self.expandBtn.isChecked():
            rootIndex = self.treeModel.index(0, 0)
            self.treeView.expand(rootIndex)
            for row in range(self.treeModel.rowCount(rootIndex)):
                index = rootIndex.child(row, 0)
                self.treeView.expand(index)
        else:
            self.treeView.collapseAll()

    def goToSearch(self):
        self.searchEdit.setText("")
        self.searchEdit.setFocus()

    def treeViewClick(self, index: QtCore.QModelIndex):
        item = self.treeModel.itemFromIndex(index)
        if item is None:  # e.g. invalid index while the model is being reset
            return
        self.library.selected_dir_row = index.row()
        self.library.selected_dir = item.dbModel.path
        self.config.updateSelectedDir(
            self.library.selected_dir, self.library.selected_dir_row
        )
        self.searchChanged()

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        # Escape is not a QShortcut on purpose: window-wide shortcuts take
        # precedence over the focused QLineEdit, which would break clearing
        # the search. Priority: clear search -> minimize (its default binding)
        if e.key() == QtCore.Qt.Key.Key_Escape:
            if self.searchEdit.hasFocus() and self.searchEdit.text():
                self.searchClear()
                return
            manager = getattr(self, "hotkeys", None)
            if manager is not None and manager.localFor("minimize") == hotkeys.ESCAPE:
                self.showMinimized()
                return
        super().keyPressEvent(e)

    def onHotkey(self, action_id):
        handlers = {
            "play_pause": self.playBtnClick,
            "next": self.next,
            "prev": self.prev,
            "minimize": self.showMinimized,
            "search": self.goToSearch,
            "skip_track": self.skipTrack,
        }
        handler = handlers.get(action_id)
        if handler is not None:
            handler()

    def applyHotkeys(self, mapping):
        """Store + activate a hotkey mapping. Returns global-registration
        failures as (label, sequence, message) triples."""
        report = self.hotkeys.apply(mapping)
        self.config.saveHotkeys(mapping)
        return report

    def searchChanged(self):
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def searchClear(self):
        self.searchEdit.setText("")
        self.selectCurrentTrack()
        self.tableView.setFocus()

    def stop(self):
        self.player.stop()
        self.updatePlayStatus()

    def updatePlayStatus(self):
        icon = (
            customui.themed_icon(self, "mdi.play")
            if self.player.isNoMusic()
            else customui.themed_icon(self, "mdi.pause")
        )
        self.playBtn.setIcon(icon)
        if self.player.isNoMusic():
            self.timer.stop()
        else:
            self.timer.start()
        self.statusbar.showMessage(self.player.getNowPlayingMsg())

    def selectCurrentTrack(self):
        currentIndex = self.tableModel.getNowPlayIndex()
        if currentIndex is not False:
            self.tableView.setCurrentIndex(currentIndex)
        else:
            print("can't move to current index, because its false")

    def stopAndPlay(self):
        self.player.stop()
        self.tableView.clearSelection()
        self.playBtnClick()

    def playBtnClick(self):
        if not self.player.now_playing:
            index = self.tableView.selectedIndexes()
            if not index:
                index = [self.tableModel.getNextIndex()]
            return self.play((index or [None])[0])

        self.player.playPause()
        self.updatePlayStatus()

    def play(self, index: QtCore.QModelIndex = None):
        if not index:
            return print("No item selected")

        item = self.tableModel.tracks[index.row()]
        # group header rows carry a dir name instead of a Track: not playable
        if not isinstance(item, Track):
            return

        track = self.player.play(index.row(), item)
        if track:
            self.selectCurrentTrack()
            self.updatePlayStatus()
            self.findLyrics()
            try:
                self.lastfm.updateNowPlaying(
                    self.player.now_playing.artist, self.player.now_playing.title
                )
            except Exception as e:
                print(str(e))

    def changeLyricsProvider(self, text):
        self.config.setLyricsProvider(self.lyricsCombo.currentText())
        if self.player.now_playing:
            self.findLyrics()

    # A plain QThread's run() is exec(): after Lyrics.run (connected to
    # started) returns, the thread's event loop keeps running until quit().
    # quit() cannot interrupt a blocking network call, and deleting a QThread
    # while it is still running aborts the process ("QThread: Destroyed while
    # thread is still running"). Superseded workers are therefore asked to
    # quit and kept referenced until they finish on their own; their late
    # results are discarded via the request counter instead of overwriting
    # the lyrics of the current track.
    def findLyrics(self):
        self._lyricsRequest += 1
        request_id = self._lyricsRequest

        for thread, _ in self._lyricsWorkers:
            thread.quit()

        thread = QThread(self)
        lyrics = Lyrics()
        # same slot-abort hazard as Lyrics.run: a config/provider error here
        # must not crash playback
        try:
            lyrics.setConfig(self.config, self.player)
        except Exception as e:
            print("Lyrics setup failed: %s" % e)
        lyrics.moveToThread(thread)

        worker = (thread, lyrics)
        self._lyricsWorkers.append(worker)

        def show(text):
            if request_id == self._lyricsRequest:
                self.lyricsTxt.setText(text)

        def cleanup():
            # Only ever reached once the thread has finished, so deleting
            # here is safe.
            if worker in self._lyricsWorkers:
                self._lyricsWorkers.remove(worker)
            lyrics.deleteLater()
            thread.deleteLater()

        # Connect signals before starting the thread
        thread.started.connect(lyrics.run)
        lyrics.finished.connect(show)
        # Leave the event loop once the lookup is done, otherwise the
        # thread stays alive forever.
        lyrics.finished.connect(thread.quit)
        thread.finished.connect(cleanup)

        thread.start()

    def next(self):
        nextIndex = self.tableModel.getNextIndex()
        if nextIndex:
            self.play(nextIndex)
            self.selectCurrentTrack()
        else:
            self.stop()

    def prev(self):
        prevIndex = self.tableModel.getPrevIndex()
        if prevIndex:
            self.play(prevIndex)
        else:
            self.stop()

    def nextRnd(self):
        rndIndex = self.tableModel.getRndIndex()
        if rndIndex:
            self.play(rndIndex)
        else:
            self.stop()

    def rescanLibrary(self, full=False):
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        start_time = time.time()

        def progress(msg):
            self.statusbar.showMessage("Scanning... " + msg)
            QtWidgets.QApplication.processEvents()

        # Only the selected subtree is rescanned; a root (or nothing)
        # selected means the whole library.
        target = self.library.selected_dir
        roots = self.library.getAllRootDirs()
        paths = roots if full or not target or target in roots else [target]

        failed = None
        try:
            self.library.rescan(paths, progress)
        except Exception as e:
            # the library list may already have changed (e.g. a dir was just
            # added): the models must refresh regardless of the scan outcome
            failed = e
            print("Library scan failed: %r" % e)
        finally:
            self._scanning = False
        self.treeModel.loadTreeData(self.treeView)
        self.tableModel.refreshPlaylist(self.searchEdit.text())
        if failed is not None:
            self.statusbar.showMessage("Scan failed: %s (try Rescan)" % failed, 5000)
            return
        self.statusbar.showMessage("Scan completed", 3000)
        print(
            "--- Library scan is completed in %s seconds ---"
            % (time.time() - start_time)
        )

    def browseDirClick(self):
        dialog = AddLibraryDirDialog(self)
        dialog.confirmed.connect(self.onDirAdded)
        dialog.formSaved.connect(self.saveAddDirForm)
        dialog.setInitialForm(self.config.getAddDirForm())
        dialog.exec()

    def saveAddDirForm(self, data):
        self.config.saveAddDirForm(json.loads(data))

    def onDirAdded(self, directory):
        if directory:
            self.config.addLibraryDir(directory)
            self.library.addDir(directory)
            # persist before scanning: an unreachable host must not make the
            # newly added library disappear on restart
            self.config.save()
            if is_sftp_path(directory):
                self.statusbar.showMessage("Checking remote agent...")
                QtWidgets.QApplication.processEvents()
            self.rescanLibrary(full=True)

    def treeContextMenu(self, pos):
        index = self.treeView.indexAt(pos)
        item = self.treeModel.itemFromIndex(index) if index.isValid() else None
        menu = QtWidgets.QMenu(self)
        if item is None:
            menu.addAction("(right-click a library to manage it)").setEnabled(False)
            menu.exec(self.treeView.viewport().mapToGlobal(pos))
            return

        root_item = item
        while root_item.parent() is not None:
            root_item = root_item.parent()
        path = root_item.dbModel.path
        label = get_root_label(path)

        rescan_action = menu.addAction("Rescan library '%s'" % label)
        menu.addSeparator()
        remove_action = menu.addAction("Remove library '%s'..." % label)

        chosen = menu.exec(self.treeView.viewport().mapToGlobal(pos))
        if chosen is rescan_action:
            self.rescanOneLibrary(path)
        elif chosen is remove_action:
            self.removeLibrary(path)

    def rescanOneLibrary(self, path):
        if getattr(self, "_scanning", False):
            return
        self._scanning = True

        def progress(msg):
            self.statusbar.showMessage("Scanning... " + msg)
            QtWidgets.QApplication.processEvents()

        failed = None
        try:
            self.library.rescan([path], progress)
        except Exception as e:
            failed = e
            print("Library scan failed: %r" % e)
        finally:
            self._scanning = False
        self.treeModel.loadTreeData(self.treeView)
        self.tableModel.refreshPlaylist(self.searchEdit.text())
        if failed is not None:
            self.statusbar.showMessage("Scan failed: %s" % failed, 5000)
        else:
            self.statusbar.showMessage("Scan completed", 3000)

    def removeLibrary(self, path):
        label = get_root_label(path)
        answer = QtWidgets.QMessageBox.question(
            self,
            "Remove library",
            "Remove library '%s'?\n\n%s\n\nThe cached tracks and folders of this "
            "library will be deleted from the database. The files themselves are "
            "not touched." % (label, path),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        if self.player.now_playing and Scanner._under(path, self.player.now_playing.full_path):
            self.stop()

        self.library.removeDir(path)
        self.library.purgeDir(path)
        self.config.removeLibraryDir(path)
        self.library.selected_dir = ""
        self.library.selected_dir_row = -1
        self.treeModel.loadTreeData(self.treeView)
        self.tableModel.refreshPlaylist(self.searchEdit.text())
        self.config.save()
        self.statusbar.showMessage("Library '%s' removed" % label, 3000)

    def setPos(self):
        self.timer.stop()
        pos = self.posSlider.value()
        self.player.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def updatePos(self):
        media_pos = int(self.player.mediaplayer.get_position() * 1000)
        self.posSlider.setValue(media_pos)
        if not self.player.mediaplayer.is_playing():
            try:
                self.lastfm.scrobble(
                    self.player.now_playing.artist, self.player.now_playing.title
                )
            except Exception as e:
                print(str(e))
            if self.stopAfterBtn.isChecked():
                # "auto" fires once; "persistent" keeps the button armed so
                # every track played afterwards stops when it ends
                if self.config.getStopAfterMode() == "auto":
                    self.stopAfterBtn.setChecked(False)
                self.stop()
            else:
                self.nextRnd() if self.rndOrderBtn.isChecked() else self.next()

    def getSelectedIndex(self):
        selectedIndex = self.tableView.selectedIndexes()
        if selectedIndex:
            return selectedIndex[0].row()
        else:
            return None

    def skipTrack(self):
        for index in list(set([i.row() for i in self.tableView.selectedIndexes()])):
            track = self.tableModel.tracks[index]
            if isinstance(track, Track):
                track.skipped = 0 if track.skipped else 1
                track.updateAttr("skipped")
                self.tableModel.tracks[index] = track
        self.tableModel.refreshPlaylist(self.searchEdit.text())

    def openSettingsDialog(self):
        dialog = SettingsDialog(self)
        dialog.confirmed.connect(self.saveSettingsFromDialog)
        dialog.geniusToken.setText(self.config.getLyricsGeniusToken())
        dialog.lastFmUsername.setText(self.config.getLastFmUsername())
        dialog.lastFmPassword.setText(self.config.getLastFmPassword())
        dialog.setAudioCachingMs(self.config.getAudioCachingMs())
        dialog.setStopAfterMode(self.config.getStopAfterMode())
        dialog.exec()

    def saveSettingsFromDialog(self, values):
        self.config.saveDialogData(json.loads(values))
        self.player.network_caching_ms = self.config.getAudioCachingMs()
        ms = self.config.getAudioCachingMs()
        self.statusbar.showMessage(
            f"Audio buffer: {ms / 1000:.1f} s (applies from the next track)",
            5000,
        )

    def setVolume(self, volume):
        self.player.setVolume(volume)

    def tableModelBeforeChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, 1)

    def tableModelChanged(self):
        for row in self.tableModel.groupRows:
            self.tableView.setSpan(row, 0, 1, Track.colCount())

    def closeEvent(self, event):
        # Ask in-flight workers to leave their event loops, then wait for
        # them: a QThread left running when the window is destroyed (it is
        # the threads' parent) would abort the process. terminate() is only
        # a last resort for threads stuck in a blocking network call.
        for thread, _ in self._lyricsWorkers:
            thread.quit()
        for thread, _ in self._lyricsWorkers:
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(1000)
        self._lyricsWorkers.clear()

        self.hotkeys.shutdown()
        get_sftp_manager().close_all()
        self.config.save()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)

    window = FooQt(app)
    window.setWindowIcon(appicon.build_icon())
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
