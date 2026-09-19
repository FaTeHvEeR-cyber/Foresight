"""Bytes -> DataFrame adapter for tabular uploads.

INTEGRATION POINT: the Phase 2 gatekeeper (MIME/magic/size/formula sanitization) should run
BEFORE this. Swap `load_tabular` for your existing tabular_parser call if you prefer; the
analytics layer only needs a DataFrame. Nothing here touches disk.
"""
from __future__ import annotations

import io

import pandas as pd


class UnsupportedFormat(ValueError):
    pass


def load_tabular(raw: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    buf = io.BytesIO(raw)
    if name.endswith((".csv", ".tsv", ".txt")):
        sep = "\t" if name.endswith(".tsv") else ","
        for enc in ("utf-8", "latin-1"):          # UCI Online Retail is latin-1
            try:
                buf.seek(0)
                return pd.read_csv(buf, sep=sep, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise UnsupportedFormat("Could not decode file as UTF-8 or Latin-1.")
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(buf)
    if name.endswith(".parquet"):
        return pd.read_parquet(buf)
    raise UnsupportedFormat(f"Unsupported tabular format: {filename!r}")
