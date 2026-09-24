"""
list_mics.py — lists every microphone speech_recognition/Windows can see,
with its index number, so you can find your headphones' exact device_index.

Run with:
    python list_mics.py
"""

import speech_recognition as sr

print("Available microphones:\n")
for index, name in enumerate(sr.Microphone.list_microphone_names()):
    print(f"  [{index}] {name}")

print("\nFind your headphones in the list above, and note its number in [brackets].")