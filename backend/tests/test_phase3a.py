import json

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from config.settings import Settings
from main import app
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.orchestrator.chart_picker import ALLOWED, pick_chart
from tests.conftest import to_csv_bytes

client = TestClient(app)


# ------------------------------------------------------------------ feature pipeline
def test_dayfirst_detected_on_bike(bike_df):
    prep = fp.prepare_series(bike_df, target="cnt")
    assert prep.date_format == "day-first"
    assert prep.cfg.label == "D" and len(prep.y) == 730
    assert prep.y.index[0] == pd.Timestamp("2018-01-01") and prep.y.index[-1] == pd.Timestamp("2019-12-31")


def test_bike_drops_ids_and_target_components(bike_df):
    prep = fp.prepare_series(bike_df, target="cnt")
    assert {"instant", "casual", "registered"} <= set(prep.dropped)
    assert "season" in prep.categorical_candidates and "holiday" in prep.categorical_candidates
    assert prep.exog.filter(regex="casual|registered|instant").shape[1] == 0


def test_airline_monthly_frequency_no_day_lags(airline_df):
    prep = fp.prepare_series(airline_df)
    assert prep.cfg.label == "M" and prep.target == "#Passengers"
    res = run_forecast(prep)
    assert res["status"] == "ok" and 7 not in res["features"]["lags"] and 12 in res["features"]["lags"]
    assert len(res["forecast"]["values"]) == 12


def test_retail_aggregation_and_flags(retail_df):
    prep = fp.prepare_series(retail_df)
    assert prep.target == "net_revenue" and prep.date_format == "month-first"
    assert prep.data_quality["cancellation_rows_dropped"] == 300
    assert prep.data_quality["zero_or_negative_price_rows_dropped"] > 0
    assert prep.data_quality["gaps_filled"] > 0          # Saturdays
    assert (prep.y >= 0).all()


def test_too_short_series_is_message_not_error():
    df = pd.DataFrame({"d": pd.date_range("2020-01-01", periods=15).strftime("%Y-%m-%d"), "v": range(15)})
    r = client.post("/api/v1/forecast", files={"file": ("s.csv", to_csv_bytes(df))}, data={"use_llm": "false"})
    assert r.status_code == 200 and r.json()["status"] == "insufficient_data" and "longer history" in r.json()["message"]


def test_expanding_encoding_is_leakage_free():
    y = np.array([10., 20, 30, 40, 50, 60])
    cat = np.array([0, 0, 0, 1, 1, 1])
    enc = fp.expanding_mean_encode(y, cat)
    y2 = y.copy(); y2[5] = 9999                          # changing the LAST row must not change any earlier encoding
    assert np.allclose(enc[:5], fp.expanding_mean_encode(y2, cat)[:5])


def test_features_never_use_current_target(bike_df):
    prep = fp.prepare_series(bike_df, target="cnt")
    lags, wins, _ = fp.select_lags(prep.cfg, len(prep.y))
    F1 = fp.build_features(prep.y, prep.exog, prep.cfg, lags, wins)
    y2 = prep.y.copy(); y2.iloc[-1] = 1e9
    F2 = fp.build_features(y2, prep.exog, prep.cfg, lags, wins)
    assert F1.iloc[-1].equals(F2.iloc[-1])


# ------------------------------------------------------------------ engines
def test_forecast_quality_and_latency_on_bike(bike_df):
    prep = fp.prepare_series(bike_df, target="cnt")
    run_forecast(prep)                                    # warm-up (xgboost import/JIT)
    res = run_forecast(prep, horizon=14)
    assert res["status"] == "ok" and len(res["forecast"]["dates"]) == 14
    assert res["metrics"]["ridge"]["r2"] > 0.5 or res["metrics"]["xgboost"]["r2"] > 0.5
    assert res["timing_ms"]["compute_total"] < 200, res["timing_ms"]
    assert all(v >= 0 for v in res["forecast"]["lower"])


def test_welch_promo_lift(promo_df):
    r = run_hypotheses(promo_df, target="Sales", group_cols=["Promo"])
    t = r["tests"][0]
    assert t["test"] == "welch_t" and t["significant"] and abs(t["lift_pct"] - 38.7) < 2


def test_wholesale_welch_and_anova(wholesale_df):
    r = run_hypotheses(wholesale_df, target="Milk")
    kinds = {t["grouping_column"]: t["test"] for t in r["tests"]}
    assert kinds == {"Channel": "welch_t", "Region": "anova"}
    assert all("p_value_adjusted" in t for t in r["tests"])
    assert any(t["skew_warning"] for t in r["tests"])


# ------------------------------------------------------------------ API
def test_forecast_endpoint_bike(bike_df):
    r = client.post("/api/v1/forecast", files={"file": ("day.csv", to_csv_bytes(bike_df))},
                    data={"target": "cnt", "use_llm": "false"})
    j = r.json()
    assert r.status_code == 200 and j["status"] == "ok"
    assert j["recommended_visualization"]["chart"] == "line_chart" and j["recommended_visualization"]["source"] == "heuristic"
    assert "within_budget" in j["timing_ms"]


def test_forecast_endpoint_retail_latin1(retail_df):
    df = retail_df.copy(); df.loc[0, "Description"] = "CAF\xc9 MUG"
    r = client.post("/api/v1/forecast", files={"file": ("online_retail.csv", to_csv_bytes(df, "latin-1"))},
                    data={"use_llm": "false"})
    assert r.status_code == 200 and r.json()["dataset"]["target"] == "net_revenue"


def test_oversize_and_bad_format(monkeypatch):
    monkeypatch.setenv("X", "1")
    import src.api.analytics_router as ar
    monkeypatch.setattr(ar, "get_settings", lambda: Settings(max_upload_bytes=100))
    assert client.post("/api/v1/forecast", files={"file": ("a.csv", b"x" * 500)}).status_code == 413
    monkeypatch.setattr(ar, "get_settings", lambda: Settings())
    assert client.post("/api/v1/forecast", files={"file": ("a.bin", b"abc")}).status_code == 415


def test_hypotheses_endpoint(wholesale_df):
    r = client.post("/api/v1/hypotheses", files={"file": ("w.csv", to_csv_bytes(wholesale_df))},
                    data={"target": "Fresh", "group_cols": "Channel,Region", "use_llm": "false"})
    j = r.json()
    assert r.status_code == 200 and len(j["tests"]) == 2 and j["recommended_visualization"]["chart"] == "bar_comparison"


def test_root_endpoints_mounted_and_gatekept(bike_df, wholesale_df):
    """Assert POST /forecast and POST /hypotheses root aliases work behind Phase 2 gatekeeper."""
    # 1. Root /forecast rejects disallowed extension (Phase 2 gatekeeper)
    r_bad = client.post("/forecast", files={"file": ("malware.bin", b"binary")})
    assert r_bad.status_code == 415

    # 2. Root /forecast accepts valid data and returns 200 with forecast
    r_fc = client.post("/forecast", files={"file": ("day.csv", to_csv_bytes(bike_df))},
                       data={"target": "cnt", "horizon": "7", "use_llm": "false"})
    assert r_fc.status_code == 200
    j_fc = r_fc.json()
    assert j_fc["status"] == "ok"
    assert len(j_fc["forecast"]["values"]) == 7

    # 3. Root /hypotheses rejects disallowed extension (Phase 2 gatekeeper)
    r_bad_hyp = client.post("/hypotheses", files={"file": ("bad.exe", b"MZ")})
    assert r_bad_hyp.status_code == 415

    # 4. Root /hypotheses accepts valid data and returns 200 with tests
    r_hyp = client.post("/hypotheses", files={"file": ("w.csv", to_csv_bytes(wholesale_df))},
                        data={"target": "Fresh", "group_cols": "Channel,Region", "use_llm": "false"})
    assert r_hyp.status_code == 200
    j_hyp = r_hyp.json()
    assert j_hyp["status"] == "ok"
    assert len(j_hyp["tests"]) == 2


# ------------------------------------------------------------------ chart picker
def _s(key="k"):
    return Settings(google_api_key=key, llm_model="gemini-3.8-flash")


def _transport(status=200, chart="line_chart"):
    def handler(req: httpx.Request):
        assert req.headers["x-goog-api-key"] == "k" and "gemini-3.8-flash" in str(req.url)
        body = json.loads(req.content)
        assert "column" not in json.dumps(body["contents"]).lower()       # no column names leave the box
        if status != 200:
            return httpx.Response(status, json={"error": "x"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({"chart": chart, "reason": "ok"})}]}}]})
    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_llm_choice_used():
    r = await pick_chart("forecast", {"status": "ok"}, settings=_s(), transport=_transport())
    assert r["source"] == "llm" and r["chart"] == "line_chart"


@pytest.mark.anyio
@pytest.mark.parametrize("kw,reason", [(dict(status=429), "llm_http_429"), (dict(chart="pie_3d"), "llm_invalid_choice")])
async def test_llm_failures_fall_back(kw, reason):
    r = await pick_chart("hypotheses", {"status": "ok", "n_tests": 2}, settings=_s(), transport=_transport(**kw))
    assert r["source"] == "heuristic" and r["chart"] == "bar_comparison" and r["fallback_reason"] == reason
    assert r["chart"] in ALLOWED


@pytest.mark.anyio
async def test_no_key_falls_back():
    r = await pick_chart("forecast", {"status": "ok"}, settings=_s(key=""))
    assert r["source"] == "heuristic" and r["fallback_reason"] == "no_api_key"
