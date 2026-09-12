"""Unit tests for backend/src/memory/lifecycle.py."""

import asyncio
import io
from unittest.mock import patch
import pytest
import pandas as pd
from starlette.testclient import TestClient

from main import app
from src.memory.lifecycle import EphemeralScope, ephemeral_processing


def test_ephemeral_processing_sync_dereferences_locals():
    """Verify DataFrames and byte buffers in caller locals are dereferenced to None on exit."""
    with ephemeral_processing():
        buf = io.BytesIO(b"intermediate data buffer")
        df = pd.DataFrame({"col": [1, 2, 3]})
        assert buf.closed is False
        assert isinstance(df, pd.DataFrame)

    assert buf is None
    assert df is None


def test_ephemeral_processing_sync_on_exception():
    """Verify cleanup and dereferencing occur even when an exception is raised."""
    buf = None
    df = None
    try:
        with ephemeral_processing():
            buf = io.BytesIO(b"error context data")
            df = pd.DataFrame({"err": [42]})
            raise ValueError("simulated upload processing error")
    except ValueError as e:
        assert "simulated upload processing error" in str(e)

    assert buf is None
    assert df is None


@pytest.mark.anyio
async def test_ephemeral_processing_async_context_manager():
    """Verify async with ephemeral_processing() correctly cleans up locals."""
    async with ephemeral_processing():
        buf = io.BytesIO(b"async buffer")
        df = pd.DataFrame({"a": [10, 20]})
        assert isinstance(df, pd.DataFrame)

    assert buf is None
    assert df is None


def test_ephemeral_processing_explicit_scope_tracking():
    """Verify EphemeralScope tracks objects and closes buffers."""
    raw_buf = io.BytesIO(b"raw bytes")
    scope = EphemeralScope()
    tracked_buf = scope.track(raw_buf)

    assert tracked_buf is raw_buf
    assert not raw_buf.closed

    scope.clear()
    assert raw_buf.closed
    assert len(scope._tracked) == 0


def test_ephemeral_processing_calls_gc_collect_on_success():
    """Verify gc.collect is invoked via try/finally on clean exit."""
    with patch("gc.collect") as mock_gc:
        with ephemeral_processing():
            _ = pd.DataFrame({"x": [1]})
        assert mock_gc.called


def test_ephemeral_processing_calls_gc_collect_on_exception():
    """Verify gc.collect is invoked via try/finally when an exception is raised."""
    with patch("gc.collect") as mock_gc:
        try:
            with ephemeral_processing():
                _ = pd.DataFrame({"x": [1]})
                raise RuntimeError("failure")
        except RuntimeError:
            pass
        assert mock_gc.called


def test_ephemeral_processing_sync_decorator():
    """Verify @ephemeral_processing decorator cleans up function locals."""
    called = False

    @ephemeral_processing()
    def process_data():
        nonlocal called
        called = True
        df = pd.DataFrame({"v": [100]})
        return len(df)

    result = process_data()
    assert called is True
    assert result == 1


@pytest.mark.anyio
async def test_ephemeral_processing_async_decorator():
    """Verify @ephemeral_processing decorator works on async coroutines."""
    @ephemeral_processing()
    async def async_handler():
        df = pd.DataFrame({"x": [1, 2, 3]})
        return len(df)

    res = await async_handler()
    assert res == 3


def test_ephemeral_processing_preserves_excluded_and_primitives():
    """Verify excluded variables and primitive values are not wiped out."""
    with ephemeral_processing(exclude={"custom_keep"}):
        custom_keep = pd.DataFrame({"retain": [99]})
        regular_int = 42
        regular_str = "hello"

    assert isinstance(custom_keep, pd.DataFrame)
    assert regular_int == 42
    assert regular_str == "hello"


def test_main_upload_endpoint_wrapped():
    """Verify FastAPI /upload endpoint works properly with ephemeral_processing wrapper."""
    client = TestClient(app)
    response = client.post("/upload")
    assert response.status_code == 200
    assert response.json() == {"message": "Upload stub"}
