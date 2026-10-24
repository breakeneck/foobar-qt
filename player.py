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

    # Resume state for pause-via-stop (see playPause): position 0..1 and
    # the resolved path of the current media
    _resume_pos: float = 0.0
    _current_path: str = ""

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
                # Resume from the saved position. play() after stop() always
                # restarts at 0, so the media is rebuilt with :start-time.
                duration = getattr(self.now_playing, "duration", 0) or 0
                start_seconds = self._resume_pos * duration
                self._start(self._current_path, start_seconds)
                if start_seconds == 0 and self._resume_pos > 0:
                    # duration unknown (e.g. some streams): seek after start
                    self.mediaplayer.set_position(self._resume_pos)
                self.paused = False
                self.onPlayStart()
            else:
                # Pause via stop(), NOT mediaplayer.pause(): VLC's pause keeps
                # the AudioUnit IO alive, and coreaudiod then holds
                # PreventUserIdleSystemSleep for this process while paused —
                # the Mac never sleeps. stop() releases the audio device and
                # the assertion. No onPlayEnd() here: the SFTP temp file must
                # survive until resume.
                self._resume_pos = self.mediaplayer.get_position()
                self.mediaplayer.stop()
                self.paused = True
        return not self.paused

    def _start(self, path, start_seconds=0.0):
        media = self.instance.media_new(path)
        # Per-media so a Settings change applies from the next track
        # without recreating the VLC instance.
        media.add_option(f":network-caching={self.network_caching_ms}")
        if start_seconds > 0:
            media.add_option(":start-time=%.3f" % start_seconds)
        self.mediaplayer.set_media(media)
        self.mediaplayer.play()

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

        self._current_path = play_path
        self._resume_pos = 0.0
        try:
            self._start(play_path)
        except Exception:
            self.paused = True
            self.now_playing = None
            return False

        self.paused = False
        self.now_playing = track
        self.now_playing_row = index
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
        self._resume_pos = 0.0
        self._current_path = ""
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
