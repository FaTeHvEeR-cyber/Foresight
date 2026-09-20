"""Phase 3A endpoints: POST /api/v1/forecast and POST /api/v1/hypotheses.

Mount in main.py:   from src.api.analytics_router import router as analytics_router
                    app.include_router(analytics_router)

Stateless: bytes -> DataFrame in RAM -> result -> references dropped + gc.collect() in `finally`.
Wrapped in ephemeral_processing() to guarantee zero-persistence and ephemeral memory lifecycles.
"""
from __future__ import annotations

import gc
import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from config.settings import get_settings
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.analytics.loader import UnsupportedFormat, load_tabular
from src.memory.lifecycle import ephemeral_processing
from src.orchestrator.chart_picker import pick_chart
from src.parsers.sanitization import gatekeep_tabular_upload, sanitize_tabular_cells

router = APIRouter(prefix="/api/v1", tags=["analytics"])


async def _read_and_validate_upload(file: UploadFile, limit: int) -> bytes:
    """Read uploaded file and route through Phase 2 security gatekeeper."""
    raw = await file.read(limit + 1)
    gatekeep_tabular_upload(
        filename=file.filename or "",
        content=raw,
        content_type=file.content_type,
        max_bytes=limit,
    )
    return raw


def _load(raw: bytes, name: str):
    """Load tabular data behind gatekeeper validation and sanitize formula injection."""
    try:
        df = load_tabular(raw, name)
    except UnsupportedFormat as e:
        raise HTTPException(415, str(e)) from e
    except Exception as e:  # unreadable table
        raise HTTPException(422, f"Could not read the file as a table: {type(e).__name__}") from e
    return sanitize_tabular_cells(df)


def _forecast_job(raw: bytes, name: str, target: Optional[str], date_col: Optional[str], horizon: Optional[int]):
    t0 = time.perf_counter()
    df = _load(raw, name)
    t_load = time.perf_counter()
    try:
        prep = fp.prepare_series(df, target=target, date_col=date_col)
        t_prep = time.perf_counter()
        res = run_forecast(prep, horizon)
    except fp.SeriesTooShort as e:
        return {"status": "insufficient_data", "message": str(e)}, (t0, t_load, time.perf_counter())
    except fp.NoDateColumn as e:
        return {"status": "no_date_column", "message": str(e)}, (t0, t_load, time.perf_counter())
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        del df
    res["timing_ms"]["load_parse"] = round((t_load - t0) * 1000, 1)
    res["timing_ms"]["prepare_series"] = round((t_prep - t_load) * 1000, 1)
    return res, (t0, t_load, t_prep)


@router.post("/forecast")
async def forecast(file: UploadFile = File(...), target: str | None = Form(None),
                   date_col: str | None = Form(None), horizon: int | None = Form(None),
                   use_llm: bool = Form(True)):
    with ephemeral_processing():
        s = get_settings()
        raw = await _read_and_validate_upload(file, s.max_upload_bytes)
        try:
            res, _ = await run_in_threadpool(_forecast_job, raw, file.filename or "", target, date_col, horizon)
        finally:
            del raw
            gc.collect()

        facts = {"status": res["status"]}
        if res["status"] == "ok":
            facts.update(frequency=res["dataset"]["frequency"], n_periods=res["dataset"]["n_periods"],
                         horizon=res["forecast"]["horizon"], skill_vs_seasonal_naive=res["skill_vs_seasonal_naive"])
            tm = res["timing_ms"]
            tm["budget"] = s.latency_budget_ms
            tm["within_budget"] = bool(tm["compute_total"] <= s.latency_budget_ms)
        res["recommended_visualization"] = await pick_chart("forecast", facts, use_llm=use_llm)
        return res


def _hypo_job(raw: bytes, name: str, target: Optional[str], group_cols: Optional[list[str]]):
    df = _load(raw, name)
    try:
        return run_hypotheses(df, target=target, group_cols=group_cols)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        del df


@router.post("/hypotheses")
async def hypotheses(file: UploadFile = File(...), target: str | None = Form(None),
                     group_cols: str | None = Form(None, description="Comma-separated column names"),
                     use_llm: bool = Form(True)):
    with ephemeral_processing():
        s = get_settings()
        raw = await _read_and_validate_upload(file, s.max_upload_bytes)
        groups = [g.strip() for g in group_cols.split(",") if g.strip()] if group_cols else None
        try:
            res = await run_in_threadpool(_hypo_job, raw, file.filename or "", target, groups)
        finally:
            del raw
            gc.collect()

        tests = res.get("tests", [])
        facts = {"status": res["status"], "n_tests": len(tests),
                 "test_types": sorted({t["test"] for t in tests}),
                 "n_significant": sum(t["significant"] for t in tests)}
        res["recommended_visualization"] = await pick_chart("hypotheses", facts, use_llm=use_llm)
        return res
