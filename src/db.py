"""
src/db.py
---------
SQLite helper for the Streamlit app.

Every time a user submits a prediction through the app, the result is logged
here.  This turns the project from 'a model in a notebook' into 'an
application' — and the Recent Transactions table on the dashboard reads from it.

Schema:
  id                INTEGER  PRIMARY KEY  AUTOINCREMENT
  amount            REAL
  transaction_type  TEXT
  hour_of_day       INTEGER
  prediction        TEXT     ('FRAUD' | 'LEGITIMATE')
  fraud_probability REAL     (0.0 – 1.0)
  risk_level        TEXT     ('HIGH' | 'MEDIUM' | 'LOW')
  timestamp         TEXT     (ISO-8601)
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("transactions.db")


def get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


def init_db() -> None:
    """Create the predictions table if it doesn't already exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            amount            REAL    NOT NULL,
            transaction_type  TEXT    NOT NULL,
            hour_of_day       INTEGER NOT NULL,
            prediction        TEXT    NOT NULL,
            fraud_probability REAL    NOT NULL,
            risk_level        TEXT    NOT NULL,
            timestamp         TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def log_prediction(
    amount: float,
    transaction_type: str,
    hour_of_day: int,
    prediction: str,
    fraud_probability: float,
    risk_level: str,
) -> None:
    """Insert one prediction record into the database."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO predictions
            (amount, transaction_type, hour_of_day, prediction, fraud_probability, risk_level, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            round(amount, 2),
            transaction_type,
            hour_of_day,
            prediction,
            round(fraud_probability, 6),
            risk_level,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_predictions(limit: int = 50):
    """Return the most recent `limit` predictions as a list of dicts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_summary_stats() -> dict:
    """Return aggregate stats used on the Dashboard page."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(*)                                     AS total,
            SUM(CASE WHEN prediction = 'FRAUD' THEN 1 ELSE 0 END) AS fraud_count,
            AVG(fraud_probability)                       AS avg_prob,
            SUM(CASE WHEN risk_level = 'HIGH'   THEN 1 ELSE 0 END) AS high_risk,
            SUM(CASE WHEN risk_level = 'MEDIUM' THEN 1 ELSE 0 END) AS med_risk,
            SUM(CASE WHEN risk_level = 'LOW'    THEN 1 ELSE 0 END) AS low_risk
        FROM predictions
    """).fetchone()
    conn.close()
    return dict(row) if row else {}
