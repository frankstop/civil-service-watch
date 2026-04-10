"""Shared utility functions for civil-service-watch."""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# ── Project root (two levels up from this file: src/ → repo root) ──────────
ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_NORM_DIR = ROOT_DIR / "data" / "normalized"
HISTORY_DIR = ROOT_DIR / "history"
DOCS_DIR = ROOT_DIR / "docs"
SOURCES_FILE = ROOT_DIR / "sources.json"

# Ensure directories exist
for _d in (DATA_RAW_DIR, DATA_NORM_DIR, HISTORY_DIR, DOCS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def today_str() -> str:
    """Return today's date as YYYY-MM-DD (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_text(text: str) -> str:
    """Return a short SHA-256 hex digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def safe_filename(source_id: str) -> str:
    """Convert a source id to a filesystem-safe filename stem."""
    return re.sub(r"[^a-z0-9_\-]", "_", source_id.lower())


def load_sources() -> list:
    """Load and return the list of sources from sources.json."""
    with open(SOURCES_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_json(path: Path) -> dict | list | None:
    """Read a JSON file; return None if it does not exist."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data, indent: int = 2) -> None:
    """Write *data* as pretty-printed JSON to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
    print(f"  wrote {path}")


def write_text(path: Path, text: str) -> None:
    """Write *text* to *path* (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"  wrote {path}")
