"""macOS Now Playing integration.

Registers the playing track with MPNowPlayingInfoCenter so it appears
globally on the Mac (Control Center, lock screen, Apple Music widget), and
attaches handlers to MPRemoteCommandCenter so the media keys work
system-wide without Accessibility permissions.

Sleep assertions: macOS creates PreventUserIdleSystemSleep through
coreaudiod on behalf of any process with active audio IO
("com.apple.audio.<device>.context.preventuseridlesleep"). VLC's pause()
keeps the AudioUnit IO alive, so the Mac stays awake while paused. The
Player pauses via stop + position restore instead (see player.py), so a
paused app holds nothing. This module never creates assertions or locks.

Remote command handlers are invoked by MediaPlayer on its own queues, not
on the Qt main thread. Handlers therefore only emit pyqtSignals; auto
connections to a main-thread receiver are queued by Qt, so UI code never
runs off the main thread.

On non-macOS platforms available() is False and every method is a no-op.
"""

import sys

from PyQt6 import QtCore

_MAC = sys.platform == "darwin"

try:
    import MediaPlayer
    from AppKit import NSImage
    from Foundation import NSData
except ImportError:
    MediaPlayer = None


class NowPlaying(QtCore.QObject):
    cmdPlay = QtCore.pyqtSignal()
    cmdPause = QtCore.pyqtSignal()
    cmdToggle = QtCore.pyqtSignal()
    cmdNext = QtCore.pyqtSignal()
    cmdPrev = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._last_elapsed = -10.0
        self._targets = []

    def available(self):
        return _MAC and MediaPlayer is not None

    def _center(self):
        return MediaPlayer.MPNowPlayingInfoCenter.defaultCenter()

    def register(self, track):
        """Publish a freshly started track and attach the media keys."""
        if not self.available():
            return
        info = {
            MediaPlayer.MPMediaItemPropertyTitle: track.title or "",
            MediaPlayer.MPMediaItemPropertyArtist: track.artist or "",
            MediaPlayer.MPMediaItemPropertyAlbumTitle: track.album or "",
            MediaPlayer.MPMediaItemPropertyPlaybackDuration: float(
                track.duration or 0
            ),
            MediaPlayer.MPNowPlayingInfoPropertyPlaybackRate: 1.0,
            MediaPlayer.MPNowPlayingInfoPropertyElapsedPlaybackTime: 0.0,
        }
        artwork = self._artwork(track.full_path)
        if artwork is not None:
            info[MediaPlayer.MPMediaItemPropertyArtwork] = artwork
        self._center().setNowPlayingInfo_(info)
        self._register_commands()
        self._active = True
        self._last_elapsed = -10.0

    def _artwork(self, path):
        """Embedded cover art, local files only (SFTP/stream paths have no
        readable tags)."""
        if not path or path.startswith(("sftp://", "http")):
            return None
        try:
            import eyed3

            audiofile = eyed3.load(path)
            if audiofile and audiofile.tag and audiofile.tag.images:
                data = audiofile.tag.images[0].image_data
                image = NSImage.imageWithData_(
                    NSData.dataWithBytes_length_(data, len(data))
                )
                if image is not None:
                    return MediaPlayer.MPMediaItemArtwork.alloc().initWithImage_(
                        image
                    )
        except Exception as e:
            print("Now Playing artwork failed: %s" % e)
        return None

    def set_paused(self, paused):
        if not self._active:
            return
        self._patch(
            {
                MediaPlayer.MPNowPlayingInfoPropertyPlaybackRate: (
                    0.0 if paused else 1.0
                )
            }
        )

    def update_position(self, elapsed):
        """Called from the 100 ms UI timer; throttled to ~1 s updates."""
        if not self._active:
            return
        if abs(elapsed - self._last_elapsed) < 0.5:
            return
        self._last_elapsed = elapsed
        self._patch(
            {
                MediaPlayer.MPNowPlayingInfoPropertyElapsedPlaybackTime: float(
                    elapsed
                )
            }
        )

    def _patch(self, changes):
        info = dict(self._center().nowPlayingInfo() or {})
        info.update(changes)
        self._center().setNowPlayingInfo_(info)

    def clear(self):
        """Stop showing anything: a stopped app must not hold Now Playing."""
        if not self.available():
            return
        self._active = False
        self._center().setNowPlayingInfo_({})

    def _register_commands(self):
        if self._targets:
            return
        cc = MediaPlayer.MPRemoteCommandCenter.sharedCommandCenter()
        for command, signal in (
            (cc.playCommand(), self.cmdPlay),
            (cc.pauseCommand(), self.cmdPause),
            (cc.togglePlayPauseCommand(), self.cmdToggle),
            (cc.nextTrackCommand(), self.cmdNext),
            (cc.previousTrackCommand(), self.cmdPrev),
        ):
            command.setEnabled_(True)
            target = command.addTargetWithHandler_(self._make_handler(signal))
            self._targets.append((command, target))

    def _make_handler(self, signal):
        def handler(event):
            signal.emit()
            return MediaPlayer.MPRemoteCommandHandlerStatusSuccess

        return handler

    def shutdown(self):
        """Detach media keys and clear Now Playing on app exit."""
        if not self.available():
            return
        for command, target in self._targets:
            try:
                command.removeTarget_(target)
            except Exception as e:
                print("remote command detach failed: %s" % e)
        self._targets = []
        self.clear()