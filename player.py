from library import Track
import vlc

paused = False
now_playing: Track = None
instance = vlc.Instance()
mediaplayer = instance.media_player_new()


def play_pause(track: Track = None, pos=0):
    global paused, now_playing

    if now_playing:
        if paused:
            mediaplayer.play()
        else:
            mediaplayer.pause()
        paused = not paused

    return not paused


def play(track: Track = None, pos=0):
    global paused, now_playing

    try:
        media = instance.media_new(track.full_path)
        # Put the media in the media player
        mediaplayer.set_media(media)
        # Parse the metadata of the file
        media.parse()
        # Set the title of the track as window title
        # setWindowTitle(media.get_meta(0))
    except:
        paused = True
        now_playing = None
        return False

    paused = False
    now_playing = track
    mediaplayer.play()

    return True



def get_progress():
    return round(mediaplayer.get_position() / 1000)


def set_progress(pos):
    mediaplayer.set_position(pos)


def stop():
    global paused, now_playing
    paused = False
    now_playing = None
    mediaplayer.stop()
