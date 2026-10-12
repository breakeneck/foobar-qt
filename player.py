import os

import vlc

import remote
from library import Track
from operating_system import LinuxStandbyLock
from virtualfs import is_sftp_path, open_file_to_temp


class Player:
    paused: bool
    now_playing_row: int
    now_playing: Track
    instance: vlc.Instance
    mediaplayer: vlc.MediaPlayer

    # Track temp files created for SFTP playback
    _last_temp_file: str = ""

    # Default VLC ring buffer (ms) for network streams. SSH-proxied audio
    # arrives in bursts; VLC's 1000 ms default underruns and stutters.
    # Overridden from config.json (audio_caching_ms), adjustable in Settings.
    DEFAULT_NETWORK_CACHING_MS = 3000

    def __init__(self):
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.paused = False
        self.now_playing_row = -1
        self.now_playing = None
        self.network_caching_ms = self.DEFAULT_NETWORK_CACHING_MS

    def onPlayStart(self):
        pass
        # LinuxStandbyLock.inhibit()

    def onPlayEnd(self):
        self._cleanup_temp()
        # LinuxStandbyLock.release()

    def _cleanup_temp(self):
        """Clean up any temp file from previous SFTP playback."""
        if self._last_temp_file:
            try:
                os.remove(self._last_temp_file)
            except OSError:
                pass
            self._last_temp_file = ""

    def playPause(self, track=None, pos=0):
        if self.now_playing:
            if self.paused:
                self.mediaplayer.play()
                self.onPlayStart()
            else:
                self.mediaplayer.pause()
                self.onPlayEnd()
            self.paused = not self.paused
        return not self.paused

    def play(self, index: int, track=None):
        # Clean up previous temp file before starting new playback
        self._cleanup_temp()

        play_path = track.full_path
        if is_sftp_path(play_path):
            # Prefer HTTP streaming through the remote agent: VLC starts
            # playing immediately and can seek via Range requests. Only fall
            # back to downloading the whole file when the agent is unusable.
            try:
                play_path = remote.stream_url(play_path)
            except Exception as e:
                print(
                    "SFTP streaming unavailable (%r); "
                    "falling back to full download" % e
                )
                try:
                    local_path, is_temp = open_file_to_temp(track.full_path)
                    play_path = local_path
                    self._last_temp_file = local_path if is_temp else ""
                except Exception as e:
                    print(f"Failed to download SFTP track for playback: {e}")
                    self.paused = True
                    self.now_playing = None
                    return False

        try:
            media = self.instance.media_new(play_path)
            # Per-media so a Settings change applies from the next track
            # without recreating the VLC instance.
            media.add_option(f":network-caching={self.network_caching_ms}")
            self.mediaplayer.set_media(media)
        except:
            self.paused = True
            self.now_playing = None
            return False

        self.paused = False
        self.now_playing = track
        self.now_playing_row = index
        self.mediaplayer.play()
        self.onPlayStart()

        return track

    def getProgress(self):
        return round(self.mediaplayer.get_position() / 1000)

    def setProgress(self, pos):
        self.mediaplayer.set_position(pos)

    def setVolume(self, volume):
        if self.now_playing is not None:
            self.mediaplayer.audio_set_volume(int(volume))

    def getVolume(self):
        return self.mediaplayer.audio_get_volume()

    def stop(self):
        self._cleanup_temp()
        self.paused = False
        self.now_playing = None
        self.now_playing_row = -1
        self.mediaplayer.stop()
        self.onPlayEnd()

    def isNoMusic(self):
        return self.paused or not self.now_playing

    def getNowPlayingMsg(self):
        if isinstance(self.now_playing, Track):
            return (
                f"{'Paused: ' if self.paused else 'Playing: '}"
                f"{self.now_playing.artist} - {self.now_playing.title}"
                f" [{self.now_playing.album}]"
            )
        else:
            return "Play stopped"
