"""SQLite store: decoded samples plus SQL views for signal health."""
import sqlite3

from . import can

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples(signal TEXT, t REAL, raw INTEGER, value REAL, error INTEGER);
CREATE INDEX IF NOT EXISTS idx_samples ON samples(signal, t);
CREATE VIEW IF NOT EXISTS signal_gaps AS
  SELECT signal, t AS gap_end, t - LAG(t) OVER (PARTITION BY signal ORDER BY t) AS gap FROM samples;
CREATE VIEW IF NOT EXISTS signal_health AS
  SELECT s.signal, COUNT(*) AS n, SUM(s.error) AS errors, ROUND(AVG(s.value), 2) AS mean_value,
         (SELECT MAX(gap) FROM signal_gaps g WHERE g.signal = s.signal) AS max_gap_s
  FROM samples s GROUP BY s.signal;
"""


def open_db(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def ingest(conn, frames):
    rows = []
    for t, cid, data in frames:
        d = can.decode(cid, data)
        if d:
            sig, raw, value, err = d
            rows.append((sig.name, t, raw, value, int(err)))
    conn.executemany("INSERT INTO samples VALUES (?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def load_series(conn):
    series = {}
    for name, t, raw, value, err in conn.execute("SELECT signal,t,raw,value,error FROM samples ORDER BY signal,t"):
        series.setdefault(name, []).append((t, raw, value, bool(err)))
    return series


def span(conn):
    return conn.execute("SELECT MIN(t), MAX(t) FROM samples").fetchone()


def health(conn):
    return conn.execute("SELECT * FROM signal_health ORDER BY signal").fetchall()
