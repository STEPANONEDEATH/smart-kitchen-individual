import sqlite3
from pathlib import Path
DB = Path(__file__).parent / 'kitchen.db'
def connect():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init():
    with connect() as c:
        c.executescript((Path(__file__).parent/'schema.sql').read_text(encoding='utf-8'))
        if c.execute('SELECT count(*) FROM owners').fetchone()[0]: return
        c.executescript((Path(__file__).parent/'seed.sql').read_text(encoding='utf-8'))
if __name__ == '__main__':
    init(); print('База инициализирована:', DB)
