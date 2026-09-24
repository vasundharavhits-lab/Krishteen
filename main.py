import threading
import webbrowser
import eel
from engine.features import *
from engine import call
from engine.command import *
from engine.scheduler import start_alarm_watcher
from engine.wakeword import start_wake_word_listener

eel.init('www')

playAssistantSound()

# Starts the background thread that fires alarms/reminders/appointments
# on time, even while the user is doing something else in the UI.
start_alarm_watcher()

# Starts the always-on "Hey Krishteen" wake-word listener. This is a plain
# Python background thread, so it keeps running even if the browser window
# is minimized — it only stops if the app itself is closed.
start_wake_word_listener()


def open_browser():
    webbrowser.open("http://localhost:8500/index.html")


threading.Timer(1.6, open_browser).start()

eel.start('index.html', mode=None, host='localhost', block=True,port=8500)