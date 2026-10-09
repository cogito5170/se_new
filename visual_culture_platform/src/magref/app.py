"""Wiring: settings -> database, storage layout, fetcher."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from . import db
from .config import Settings
from .http import Fetcher, Transport, build_transport
from .storage import Layout


@dataclass
class App:
    settings: Settings
    conn: sqlite3.Connection
    layout: Layout
    transport: Transport
    fetcher: Fetcher

    def close(self) -> None:
        self.conn.close()


def open_app(settings: Settings, transport: Transport | None = None, sleep=time.sleep) -> App:
    if settings.fixture_dir is not None:
        # Local files: no remote server to protect, so no politeness delay.
        settings = settings.with_overrides(request_interval=0.0)
    layout = Layout(settings.data_dir)
    layout.ensure()
    conn = db.connect(settings.database_path)
    transport = transport or build_transport(settings, allow_loopback=settings.allow_loopback)
    fetcher = Fetcher(settings, transport, sleep=sleep, allow_loopback=settings.allow_loopback)
    return App(settings, conn, layout, transport, fetcher)
