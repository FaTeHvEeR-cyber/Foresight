"""FastAPI Route Handler for Segmentation and Outlier Detection: POST /api/v1/segmentation.

Stateless & Ephemeral:
- Bytes -> DataFrame in RAM -> Segmentation Engine -> Dereferencing + gc.collect() in finally.
- Wrapped in ephemeral_processing() to guarantee zero-persistence.
- Dynamic visualization picking via chart_picker (LLM with deterministic heuristic fallback).
"""
from __future__ import annotations

import gc
import time
from typing import Any, Dict, Tuple

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from config.settings import get_settings
from src.analytics.loader import UnsupportedFormat, load_tabular
from src.analytics.outlier_engine import run_segmentation
from src.memory.lifecycle import ephemeral_processing
from src.orchestrator.chart_picker import pick_chart
from src.parsers.sanitization import gatekeep_tabular_upload, sanitize_tabular_cells
from src.schemas.segmentation import SegmentationResponse

router = APIRouter(prefix="/api/v1", tags=["analytics"])
root_router = APIRouter(tags=["analytics"])


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
        return sanitize_tabular_cells(df)
    except UnsupportedFormat as e:
        raise HTTPException(415, str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f"Could not read the file as a table: {type(e).__name__}") from e


def _segmentation_job(raw: bytes, name: str) -> Tuple[Dict[str, Any], float]:
    """Execute in-memory segmentation compute inside worker thread."""
    t0 = time.perf_counter()
    df = _load(raw, name)
    t_load = time.perf_counter()
    try:
        res = run_segmentation(df)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Segmentation computation error: {type(e).__name__}") from e
    finally:
        del df
        gc.collect()

    load_parse_ms = round((t_load - t0) * 1000, 1)
    if "timing_ms" in res and isinstance(res["timing_ms"], dict):
        res["timing_ms"]["load_parse"] = load_parse_ms

    return res, load_parse_ms


@router.post("/segmentation", response_model=SegmentationResponse)
@root_router.post("/segmentation", response_model=SegmentationResponse)
async def segmentation(
    file: UploadFile = File(...),
    use_llm: bool = Form(True),
):
    """Run unsupervised segmentation, KMeans clustering, and IsolationForest outlier analysis.

    Pure in-memory execution, guaranteed ephemeral lifecycle, and sub-200ms latency budget.
    """
    with ephemeral_processing():
        s = get_settings()
        raw = await _read_and_validate_upload(file, s.max_upload_bytes)
        try:
            job_result = await run_in_threadpool(
                _segmentation_job, raw, file.filename or ""
            )
            res: Dict[str, Any] = job_result[0]
        finally:
            del raw
            gc.collect()

        facts: Dict[str, Any] = {
            "status": res["status"],
            "optimal_k": res.get("optimal_k", 4),
            "n_samples": res.get("original_row_count", 0),
            "n_outliers": res.get("n_outliers", 0),
            "has_correlation_data": bool(
                res.get("correlation_matrix", {}).get("columns")
            ),
        }

        # Chart recommendation via chart_picker (§5) - never hardcoded
        res["recommended_visualization"] = await pick_chart(
            "segmentation", facts, use_llm=use_llm
        )

        return res
