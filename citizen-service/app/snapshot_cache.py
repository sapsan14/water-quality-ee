"""Isolated cached snapshot loader.

The `@st.cache_data`-decorated function lives in its own small module so that
Streamlit's cache-key computation can call ``inspect.getsource()`` on a clean,
minimal file. On Python 3.14, running ``inspect.getsource()`` against the
large ``streamlit_app.py`` module (which embeds multi-line CSS/JS strings and
HTML snippets) can trigger ``tokenize.TokenError`` inside
``streamlit.runtime.caching.cache_utils._make_function_key``. Keeping the
cached function here sidesteps that problem entirely.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "citizen-service" / "artifacts" / "snapshot.json"

_LOG = logging.getLogger("citizen.streamlit")


@st.cache_data(show_spinner=False)
def load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.is_file():
        _LOG.warning("Файл снимка отсутствует: %s", SNAPSHOT_PATH)
        return None
    st_sz = SNAPSHOT_PATH.stat().st_size
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _LOG.info(
        "Снимок загружен с диска в кэш Streamlit (%s байт, generated_at=%s)",
        st_sz,
        (data or {}).get("generated_at"),
    )
    return data
