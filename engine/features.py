import os
import re
import sqlite3
import urllib.parse
import webbrowser
from playsound import playsound
import eel

from engine.command import speak
from engine.config import ASSISTANT_NAME, DB_NAME
import pywhatkit as kit


conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS sys_command (
        name TEXT NOT NULL,
        path TEXT NOT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS web_command (
        name TEXT NOT NULL,
        url TEXT NOT NULL
    )
''')

_DEFAULT_WEB_COMMANDS = [
    ("youtube", "https://www.youtube.com"),
    ("google", "https://www.google.com"),
    ("gmail", "https://mail.google.com"),
    ("facebook", "https://www.facebook.com"),
    ("instagram", "https://www.instagram.com"),
    ("twitter", "https://www.twitter.com"),
    ("whatsapp", "https://web.whatsapp.com"),
    ("amazon", "https://www.amazon.com"),
    ("wikipedia", "https://www.wikipedia.org"),
    ("chatgpt", "https://chat.openai.com"),
]
cursor.execute('SELECT COUNT(*) FROM web_command')
if cursor.fetchone()[0] == 0:
    cursor.executemany('INSERT INTO web_command (name, url) VALUES (?, ?)', _DEFAULT_WEB_COMMANDS)
    conn.commit()


def playAssistantSound():
    music_dir = "www\\assets\\audio\\start_sound.mp3"
    try:
        playsound(music_dir)
    except Exception as e:
        print("Could not play start sound:", e)


@eel.expose
def playClickSound():
    music_dir = "www\\assets\\audio\\click_sound.mp3"
    try:
        playsound(music_dir)
    except Exception as e:
        print("Could not play click sound:", e)


def openCommand(query):
    # FIX: query arrives already lowercased from command.py, but
    # ASSISTANT_NAME is "Krishteen" (capital K) — the old .replace() never
    # matched anything because of the case mismatch, so the assistant's
    # name was never actually being stripped out of "Krishteen open X".
    query = query.replace(ASSISTANT_NAME.lower(), "")
    query = query.replace("open", "").strip().lower()

    if query == "":
        return

    try:
        cursor.execute('SELECT path FROM sys_command WHERE LOWER(name) = ?', (query,))
        results = cursor.fetchall()

        if len(results) != 0:
            speak("Opening " + query)
            os.startfile(results[0][0])
            return

        cursor.execute('SELECT url FROM web_command WHERE LOWER(name) = ?', (query,))
        results = cursor.fetchall()

        if len(results) != 0:
            speak("Opening " + query)
            webbrowser.open(results[0][0])
            return

    except sqlite3.OperationalError as e:
        print("openCommand DB error:", e)

    speak("Opening " + query)
    single_word = query.replace(" ", "")
    if single_word.isalnum():
        webbrowser.open(f"https://www.{single_word}.com")
    else:
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")


def PlayYoutube(query):
    search_term = extract_yt_term(query)
    if search_term:
        speak("Playing " + search_term + " on YouTube")
        kit.playonyt(search_term)
    else:
        speak("Sorry, I couldn't find what to play on YouTube.")


def extract_yt_term(command):
    pattern = r'play\s+(.*?)\s+on\s+youtube'
    match = re.search(pattern, command, re.IGNORECASE)
    return match.group(1) if match else None