"""Pydantic v2 schemas for Segmentation and Outlier Analysis (POST /api/v1/segmentation)."""
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class HeatmapPoint(BaseModel):
    x: str = Field(description="X variable name")
    y: str = Field(description="Y variable name")
    value: float = Field(description="Pearson correlation coefficient between -1.0 and 1.0")


class CorrelationMatrix(BaseModel):
    columns: List[str] = Field(description="Ordered list of variable names included in the matrix")
    values: List[List[float]] = Field(description="2D correlation coefficients array [row][col]")
    points: List[HeatmapPoint] = Field(
        default_factory=list,
        description="Flattened list of {x, y, value} objects for heatmap rendering",
    )
    truncated: bool = Field(
        default=False,
        description="True if original numeric feature count exceeded cap and was truncated by variance",
    )


class ScatterPoint(BaseModel):
    x: float = Field(description="PCA dimension 1 projection")
    y: float = Field(description="PCA dimension 2 projection")
    clusterId: int = Field(description="Assigned KMeans cluster integer ID")


class RecommendedVisualization(BaseModel):
    charts: List[str] = Field(description="Ranked list of recommended chart types (max 3)")
    chart: str = Field(description="Primary backward-compatible chart token")
    reason: str = Field(description="Rationale for chart recommendation")
    source: str = Field(default="heuristic", description="'llm' or 'heuristic'")
    allowed: List[str] = Field(default_factory=list, description="All allowed chart tokens in registry")
    model: Optional[str] = Field(default=None, description="LLM model used if source is 'llm'")
    fallback_reason: Optional[str] = Field(default=None, description="Fallback reason if LLM was bypassed")
    latency_ms: Optional[float] = Field(default=None, description="Time taken to select visualization in ms")


class SegmentationResponse(BaseModel):
    status: str = Field(default="ok", description="Response status: 'ok' or error/degraded reason")
    message: Optional[str] = Field(default=None, description="Status detail or advisory message")
    optimal_k: int = Field(description="Selected number of clusters K")
    clustering_method: str = Field(
        description="Selection method: 'data_driven_silhouette' (peak silhouette >= 0.40) or 'fallback_default' (K=4)"
    )
    pca_x: List[float] = Field(
        description="Array of 2D PCA x coordinates (capped at 10,000 points, outliers preserved)"
    )
    pca_y: List[float] = Field(
        description="Array of 2D PCA y coordinates (capped at 10,000 points, outliers preserved)"
    )
    cluster_assignments: List[int] = Field(
        description="Cluster assignment label for each returned scatter point"
    )
    outlier_records: List[dict[str, Any]] = Field(
        description="Top 100 outlier records ordered descending by anomaly score, carrying id and original values"
    )
    correlation_matrix: CorrelationMatrix = Field(
        description="Correlation matrix of features used for clustering, computed pre-scaling"
    )
    correlation_matrix_truncated: bool = Field(
        default=False,
        description="True if numeric columns exceeded the cap (25-50 cols) and were truncated by variance",
    )
    subsampled: bool = Field(
        default=False,
        description="True if the input dataset exceeded the 20,000 row ceiling and was subsampled",
    )
    original_row_count: int = Field(
        description="Total observation count prior to live fit subsampling"
    )
    recommended_visualization: RecommendedVisualization = Field(
        description="Visualization recommendation payload"
    )

    # Optional convenience & frontend compatibility aliases
    clusterCount: Optional[int] = Field(default=None, description="CamelCase alias for optimal_k")
    clusters: Optional[List[int]] = Field(default=None, description="Alias for cluster_assignments")
    points: Optional[List[ScatterPoint]] = Field(
        default=None,
        description="Array of {x, y, clusterId} scatter points for frontend ScatterCluster component",
    )
    outlier_mask: Optional[List[bool]] = Field(
        default=None,
        description="Boolean array indicating whether each returned scatter point is a flagged outlier",
    )
    outlierMask: Optional[List[bool]] = Field(
        default=None,
        description="CamelCase alias for outlier_mask matching frontend component expectations",
    )
    outlier_score_method: str = Field(
        default="isolation_forest",
        description="Anomaly detection algorithm used",
    )
    outlierScoreMethod: str = Field(
        default="isolation_forest",
        description="CamelCase alias for outlier_score_method",
    )
    features_used: Optional[List[str]] = Field(
        default=None,
        description="Names of numeric columns utilized in clustering and outlier scoring",
    )
    n_outliers: Optional[int] = Field(
        default=None,
        description="Total number of observations flagged as outliers under the 3% contamination rate",
    )
    contamination: float = Field(
        default=0.03,
        description="Configured contamination rate for IsolationForest (fixed 0.03)",
    )
    timing_ms: Optional[dict[str, Any]] = Field(
        default=None,
        description="Detailed execution timing breakdown in milliseconds",
    )
