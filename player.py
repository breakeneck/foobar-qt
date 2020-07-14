import library
import vlc

paused = False
now_playing_row: -1
now_playing: library.Track = None
stop_after = False
instance = vlc.Instance()
mediaplayer = instance.media_player_new()


def play_pause(track: library.Track = None, pos=0):
    global paused

    if now_playing:
        if paused:
            mediaplayer.play()
        else:
            mediaplayer.pause()
        paused = not paused
    return not paused

def play(index: int, track: library.Track = None):
    global paused, now_playing, now_playing_row

    try:
        media = instance.media_new(track.full_path)
        mediaplayer.set_media(media)
        # media.parse()
        # setWindowTitle(media.get_meta(0))
    except:
        paused = True
        now_playing = None
        return False

    paused = False
    now_playing = track
    now_playing_row = index
    mediaplayer.play()

    return track



def get_progress():
    return round(mediaplayer.get_position() / 1000)


def set_progress(pos):
    mediaplayer.set_position(pos)


def stop():
    global paused, now_playing
    paused = False
    now_playing = None
    mediaplayer.stop()

def getNowPlayingMsg():
    return f'{now_playing.artist} - {now_playing.title} [{now_playing.album}]'