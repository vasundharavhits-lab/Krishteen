import sqlite3
from engine.config import DB_NAME

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()
conn.close()