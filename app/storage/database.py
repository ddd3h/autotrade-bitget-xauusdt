import sqlite3
import pandas as pd
from datetime import datetime
from typing import Any, Optional
from app.config import settings
from app.logger import export_logger as logger

class StorageService:
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    entry_time TEXT,
                    exit_price REAL,
                    exit_time TEXT,
                    quantity REAL,
                    gross_pnl REAL,
                    fee REAL,
                    slippage REAL,
                    funding REAL,
                    net_pnl REAL,
                    exit_reason TEXT
                )
            """)
            # Migration: Add mode column if not exists
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN mode TEXT")
            except sqlite3.OperationalError:
                pass # Already exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    timestamp TEXT,
                    level TEXT,
                    message TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_status (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def save_trade(self, trade_data: dict):
        with sqlite3.connect(self.db_path) as conn:
            columns = ', '.join(trade_data.keys())
            placeholders = ', '.join(['?' for _ in trade_data])
            sql = f"INSERT OR REPLACE INTO trades ({columns}) VALUES ({placeholders})"
            conn.execute(sql, list(trade_data.values()))

    def log_event(self, level: str, message: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO events VALUES (?, ?, ?)", (datetime.utcnow().isoformat(), level, message))

    def save_status(self, key: str, value: Any):
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO system_status VALUES (?, ?)", (key, json.dumps(value)))

    def get_status(self, key: str) -> Any:
        import json
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM system_status WHERE key = ?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def get_recent_trades(self, limit: int = 20, mode: Optional[str] = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM trades"
            params = []
            if mode:
                sql += " WHERE mode = ?"
                params.append(mode)
            sql += " ORDER BY exit_time DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_equity_curve(self, mode: Optional[str] = None):
        with sqlite3.connect(self.db_path) as conn:
            sql = "SELECT exit_time, net_pnl FROM trades"
            params = []
            if mode:
                sql += " WHERE mode = ?"
                params.append(mode)
            sql += " ORDER BY exit_time ASC"
            rows = conn.execute(sql, params).fetchall()
            curve = []
            current = settings.INITIAL_EQUITY
            for row in rows:
                current += row[1]
                curve.append({"time": row[0], "equity": current})
            return curve
