"""Analytics package for time-series forecasting and hypothesis testing."""
from src.analytics.feature_pipeline import (
    FreqConfig,
    FREQ_CONFIGS,
    PreparedSeries,
    SeriesTooShort,
    NoDateColumn,
    prepare_series,
    build_features,
    select_lags,
    expanding_mean_encode,
    fit_mean_lookup,
)
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.analytics.loader import load_tabular, UnsupportedFormat

__all__ = [
    "FreqConfig",
    "FREQ_CONFIGS",
    "PreparedSeries",
    "SeriesTooShort",
    "NoDateColumn",
    "prepare_series",
    "build_features",
    "select_lags",
    "expanding_mean_encode",
    "fit_mean_lookup",
    "run_forecast",
    "run_hypotheses",
    "load_tabular",
    "UnsupportedFormat",
]
