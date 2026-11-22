import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, source BLOB NOT NULL, book BLOB NOT NULL,
  result TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  run_id TEXT NOT NULL REFERENCES runs(id), version INTEGER NOT NULL,
  decision TEXT NOT NULL, note TEXT NOT NULL, changed TEXT NOT NULL,
  PRIMARY KEY(run_id,version)
);
CREATE TABLE IF NOT EXISTS tails (
  id TEXT PRIMARY KEY, length INTEGER NOT NULL CHECK (length > 0),
  home TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('在库','预占','借出','已领用')),
  holder TEXT, loan INTEGER, seq INTEGER NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS loans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tail TEXT NOT NULL REFERENCES tails(id), borrower TEXT NOT NULL,
  lent TEXT NOT NULL, returned TEXT
);
CREATE TABLE IF NOT EXISTS claims (
  request TEXT PRIMARY KEY,
  tail TEXT NOT NULL REFERENCES tails(id), batch TEXT NOT NULL,
  length INTEGER NOT NULL, created TEXT NOT NULL
);
"""


@contextmanager
def connection():
    path = Path(settings.DB)
    path.parent.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(path,timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()
