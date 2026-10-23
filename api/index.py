"""FastAPI service for the UPI-style fraud-detection capstone.

This service deliberately keeps inference separate from the Next.js user
interface. It serves an instant, transaction-level prediction from saved
artifacts; it is not connected to NPCI, a bank, or a live UPI network.

Run locally from the repository root:
    uvicorn api.index:app --reload --port 8000
"""

from __future__ import annotations

import io
import json
import os
import sys
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

# Ensure repository root and api directory are in sys.path for serverless runtimes
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in [str(_ROOT), str(_HERE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from pydantic import BaseModel, Field, field_validator
from sklearn.metrics import (
    accuracy_score,
    auc,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split

try:
    from api.database import (
        get_recent_predictions,
        initialise_database,
        record_prediction,
        status as database_status,
    )
except Exception as _db_exc:
    warnings.warn(f"Database module unavailable: {_db_exc}")

    def database_status() -> dict[str, Any]:
        return {"configured": False, "available": False, "last_error": str(_db_exc)}

    def get_recent_predictions(limit: int = 10) -> list[dict[str, Any]]:
        return []

    def record_prediction(**kwargs: Any) -> bool:
        return False

    def initialise_database() -> bool:
        return False

# Razorpay payment integration (optional — graceful if deps missing)
try:
    from api.payment_integration.razorpay_integration import (
        router as payment_router,
        init_payment_tables,
    )
    _PAYMENTS_AVAILABLE = True
except Exception as _p_exc:
    warnings.warn(f"Payment integration disabled: {_p_exc}")
    _PAYMENTS_AVAILABLE = False


def _find_path(*parts: str) -> Path:
    rel = Path(*parts)
    for base in [_ROOT, _HERE, Path.cwd(), Path("/var/task")]:
        candidate = base / rel
        if candidate.exists():
            return candidate
    return _ROOT / rel


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = _find_path("models")
DATA_PATH = _find_path("data", "transactions.csv")

# PaySim-like raw columns accepted by the fitted preprocessor. The training
# metadata can override this list, protecting inference from schema changes.
DEFAULT_RAW_FEATURE_COLUMNS = [
    "step",
    "type",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
]
TRANSACTION_TYPES = {"CASH_OUT", "PAYMENT", "TRANSFER", "CASH_IN", "DEBIT"}

_MODEL: Any | None = None
_PREPROCESSOR: Any | None = None
_DATASET: pd.DataFrame | None = None
_META: dict[str, Any] = {}
_FEATURE_IMPORTANCES: pd.DataFrame | None = None
_LOAD_ERRORS: list[str] = []


def _load_artifacts() -> None:
    """Load model artifacts once per API process/cold start."""
    global _MODEL, _PREPROCESSOR, _DATASET, _META, _FEATURE_IMPORTANCES, _LOAD_ERRORS

    if _MODEL is not None and _PREPROCESSOR is not None and _DATASET is not None:
        return

    _LOAD_ERRORS = []

    dataset_file = DATA_PATH
    if not dataset_file.is_file():
        sample_file = _find_path("data", "sample_transactions.csv")
        if sample_file.is_file():
            dataset_file = sample_file

    artifact_paths = {
        "model": MODELS_DIR / "fraud_model.pkl",
        "preprocessor": MODELS_DIR / "preprocessor.pkl",
        "metadata": MODELS_DIR / "model_meta.json",
        "feature importances": MODELS_DIR / "feature_importances.csv",
        "dataset": dataset_file,
    }

    try:
        _MODEL = joblib.load(artifact_paths["model"])
    except Exception as exc:
        _MODEL = None
        _LOAD_ERRORS.append(f"model: {exc}")

    try:
        _PREPROCESSOR = joblib.load(artifact_paths["preprocessor"])
    except Exception as exc:
        _PREPROCESSOR = None
        _LOAD_ERRORS.append(f"preprocessor: {exc}")

    try:
        with artifact_paths["metadata"].open(encoding="utf-8") as file:
            _META = json.load(file)
    except Exception as exc:
        _META = {}
        _LOAD_ERRORS.append(f"metadata: {exc}")

    try:
        _DATASET = pd.read_csv(artifact_paths["dataset"])
    except Exception as exc:
        _DATASET = None
        _LOAD_ERRORS.append(f"dataset: {exc}")

    try:
        _FEATURE_IMPORTANCES = pd.read_csv(artifact_paths["feature importances"])
    except Exception:
        # Feature importance is model-dependent, so its absence is not an API
        # failure (for example, Logistic Regression may be selected).
        _FEATURE_IMPORTANCES = None


def _raw_feature_columns() -> list[str]:
    columns = _META.get("raw_feature_columns", DEFAULT_RAW_FEATURE_COLUMNS)
    return list(columns)


def _require_dataset() -> pd.DataFrame:
    if _DATASET is None:
        _load_artifacts()
    if _DATASET is None:
        raise HTTPException(503, "Dataset is not loaded. Check the API health endpoint.")
    return _DATASET


def _require_inference_artifacts() -> tuple[Any, Any]:
    if _MODEL is None or _PREPROCESSOR is None:
        _load_artifacts()
    if _MODEL is None or _PREPROCESSOR is None:
        raise HTTPException(
            503,
            "Model artifacts are not loaded. Run 'python src/train_model.py' first.",
        )
    return _MODEL, _PREPROCESSOR


def _raw_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Select and validate the raw feature schema accepted by the preprocessor."""
    expected = _raw_feature_columns()
    missing = [column for column in expected if column not in frame.columns]
    if missing:
        raise HTTPException(
            503,
            f"Dataset/artifact schema mismatch. Missing raw features: {', '.join(missing)}",
        )
    return frame.loc[:, expected].copy()


def _high_value_threshold() -> float | None:
    value = _META.get("high_value_threshold")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _risk_level(probability: float) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if probability >= 0.70:
        return "HIGH"
    if probability >= 0.30:
        return "MEDIUM"
    return "LOW"


def _fraud_probabilities(model: Any, transformed: Any) -> np.ndarray:
    """Get class-1 probabilities without leaking harmless BLAS warning noise.

    On some local macOS/NumPy combinations, ``LogisticRegression`` emits
    spurious ``matmul`` overflow warnings while calculating a finite, valid
    decision function for an entire batch. We filter only those exact runtime
    messages; real preprocessing and prediction errors still propagate.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*encountered in matmul",
            category=RuntimeWarning,
        )
        return np.asarray(model.predict_proba(transformed)[:, 1], dtype=float)


def _dataset_info() -> dict[str, Any]:
    provenance = _META.get("dataset_provenance", {})
    if not provenance:
        provenance = {
            "source": "Dataset provenance has not yet been recorded.",
            "real_upi_network_data": False,
            "validation_note": "Confirm the source before presenting model results.",
        }
    return provenance


def _feature_importance_data(model: Any) -> list[dict[str, Any]]:
    """Return a chart-ready, model-agnostic top-feature list."""
    if _FEATURE_IMPORTANCES is not None and not _FEATURE_IMPORTANCES.empty:
        columns = set(_FEATURE_IMPORTANCES.columns)
        if {"feature", "importance"}.issubset(columns):
            data = _FEATURE_IMPORTANCES.loc[:, ["feature", "importance"]]
        else:
            # Support the older CSV shape produced by ``Series.to_csv``.
            data = _FEATURE_IMPORTANCES.iloc[:, :2].copy()
            data.columns = ["feature", "importance"]
        data = data.sort_values("importance", ascending=False).head(15)
        return [
            {"feature": str(row.feature), "importance": round(float(row.importance), 6)}
            for row in data.itertuples(index=False)
        ]

    feature_names = list(_META.get("feature_names", []))
    if hasattr(model, "feature_importances_") and feature_names:
        values = model.feature_importances_
    elif hasattr(model, "coef_") and feature_names:
        values = np.abs(np.ravel(model.coef_))
    else:
        return []

    return [
        {"feature": name, "importance": round(float(value), 6)}
        for name, value in sorted(
            zip(feature_names, values), key=lambda pair: pair[1], reverse=True
        )[:15]
    ]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Keep startup non-blocking for serverless cold-starts.
    # Database tables are already created and artifacts load lazily on demand.
    yield


app = FastAPI(
    title="UPI-Style Fraud Detection API",
    description=(
        "Inference API for an educational ML prototype using a digital-payments "
        "dataset. It is not connected to NPCI, a bank, or the live UPI network."
    ),
    version="1.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

class StripVercelPrefixMiddleware:
    """Pure ASGI middleware to normalize paths rewritten by Vercel."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/api/index"):
                new_path = path[len("/api/index") :]
                if not new_path.startswith("/"):
                    new_path = "/" + new_path
                scope["path"] = new_path
        await self.app(scope, receive, send)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(StripVercelPrefixMiddleware)

# Include Razorpay payment routes if the integration is installed.
if _PAYMENTS_AVAILABLE:
    app.include_router(payment_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import traceback
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "exception_type": type(exc).__name__,
            "detail": str(exc),
            "traceback": traceback.format_exc().splitlines()[-10:],
        },
    )


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: Any) -> JSONResponse:
    detail = getattr(exc, "detail", None) or "Not Found"
    return JSONResponse(
        status_code=404,
        content={
            "detail": detail,
            "received_path": request.url.path,
            "scope_path": request.scope.get("path"),
            "scope_root_path": request.scope.get("root_path"),
        },
    )



class TransactionInput(BaseModel):
    """Fields a user can provide for a PaySim-schema transaction."""

    amount: float = Field(..., gt=0, description="Transaction amount in INR")
    transaction_type: str = Field(..., description="PaySim transaction category")
    hour_of_day: int = Field(..., ge=0, le=23, description="Hour from 0 to 23")
    step: Optional[int] = Field(default=None, ge=1, le=744, description="Optional simulation step 1-744")
    old_balance_orig: float = Field(default=0.0, ge=0)
    new_balance_orig: float = Field(default=0.0, ge=0)
    old_balance_dest: float = Field(default=0.0, ge=0)
    new_balance_dest: float = Field(default=0.0, ge=0)

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in TRANSACTION_TYPES:
            accepted = ", ".join(sorted(TRANSACTION_TYPES))
            raise ValueError(f"transaction_type must be one of: {accepted}")
        return normalized


class PredictionResponse(BaseModel):
    prediction: Literal["FRAUD", "LEGITIMATE"]
    fraud_probability: float
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    error_balance_orig: float
    error_balance_dest: float
    is_high_value: bool
    saved_to_history: bool


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "UPI-style fraud-detection ML prototype API"}


@app.get("/ping")
@app.get("/api/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
@app.get("/health")
def health() -> dict[str, Any]:
    """Health and artifact-readiness information for deployment checks."""
    if _MODEL is None or _PREPROCESSOR is None or _DATASET is None:
        try:
            _load_artifacts()
        except Exception:
            pass

    return {
        "status": "ok" if _MODEL is not None and _PREPROCESSOR is not None else "degraded",
        "model_loaded": _MODEL is not None,
        "preprocessor_loaded": _PREPROCESSOR is not None,
        "dataset_loaded": _DATASET is not None,
        "database": database_status(),
        "load_errors": _LOAD_ERRORS,
    }


@app.get("/api/dataset-info")
@app.get("/dataset-info")
def dataset_info() -> dict[str, Any]:
    """Expose honest dataset provenance and schema for the About/EDA views."""
    dataset = _require_dataset()
    return {
        "rows": int(len(dataset)),
        "columns": list(dataset.columns),
        "target_column": _META.get("target_column", "isFraud"),
        "provenance": _dataset_info(),
    }


@app.get("/api/stats")
@app.get("/stats")
def stats() -> dict[str, Any]:
    """Dataset-level KPIs for the dashboard; never fabricated values."""
    dataset = _require_dataset()
    if "isFraud" not in dataset.columns or "amount" not in dataset.columns:
        raise HTTPException(503, "Dataset is missing isFraud or amount columns.")

    total = len(dataset)
    fraud_count = int(dataset["isFraud"].sum())
    return {
        "total_transactions": int(total),
        "fraud_count": fraud_count,
        "legit_count": int(total - fraud_count),
        "fraud_rate": round(float(dataset["isFraud"].mean() * 100), 4),
        "avg_amount": round(float(dataset["amount"].mean()), 2),
        "max_amount": round(float(dataset["amount"].max()), 2),
        "model_name": _META.get("best_model_name", "Not trained"),
        "dataset_source": _dataset_info().get("source", "Unknown"),
    }


@app.post("/api/predict", response_model=PredictionResponse)
def predict(transaction: TransactionInput) -> PredictionResponse:
    """Produce one instant prediction from saved, never-retrained artifacts."""
    model, preprocessor = _require_inference_artifacts()

    step_value = (
        transaction.step
        if transaction.step is not None
        else (15 * 24 + transaction.hour_of_day)
    )
    raw_input = pd.DataFrame(
        [
            {
                "step": step_value,
                "type": transaction.transaction_type,
                "amount": transaction.amount,
                "oldbalanceOrg": transaction.old_balance_orig,
                "newbalanceOrig": transaction.new_balance_orig,
                "oldbalanceDest": transaction.old_balance_dest,
                "newbalanceDest": transaction.new_balance_dest,
            }
        ]
    )

    try:
        transformed = preprocessor.transform(_raw_features(raw_input))
        probability = float(_fraud_probabilities(model, transformed)[0])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not preprocess this transaction: {exc}") from exc

    decision_threshold = float(_META.get("prediction_threshold", 0.5))
    prediction: Literal["FRAUD", "LEGITIMATE"] = (
        "FRAUD" if probability >= decision_threshold else "LEGITIMATE"
    )
    high_value_threshold = _high_value_threshold()
    is_high_value = (
        transaction.amount > high_value_threshold
        if high_value_threshold is not None
        else False
    )
    error_balance_orig = (
        transaction.new_balance_orig + transaction.amount - transaction.old_balance_orig
    )
    error_balance_dest = (
        transaction.old_balance_dest + transaction.amount - transaction.new_balance_dest
    )
    risk_level = _risk_level(probability)

    saved_to_history = record_prediction(
        amount=transaction.amount,
        transaction_type=transaction.transaction_type,
        hour_of_day=transaction.hour_of_day,
        prediction=prediction,
        fraud_probability=probability,
        risk_level=risk_level,
    )

    return PredictionResponse(
        prediction=prediction,
        fraud_probability=round(probability, 6),
        risk_level=risk_level,
        error_balance_orig=round(error_balance_orig, 2),
        error_balance_dest=round(error_balance_dest, 2),
        is_high_value=is_high_value,
        saved_to_history=saved_to_history,
    )


@app.get("/api/predictions")
def recent_predictions(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    """Return Neon-backed history when ``DATABASE_URL`` is configured."""
    return {
        "predictions": get_recent_predictions(limit),
        "persistence": database_status(),
    }


@app.get("/api/charts/fraud-by-type")
def chart_fraud_by_type() -> list[dict[str, Any]]:
    dataset = _require_dataset()
    required = {"type", "isFraud"}
    if not required.issubset(dataset.columns):
        raise HTTPException(503, "Dataset cannot produce the transaction-type chart.")

    grouped = (
        dataset.groupby("type", observed=True)["isFraud"]
        .agg(total="count", fraud="sum")
        .reset_index()
    )
    grouped["fraud_rate"] = grouped["fraud"] / grouped["total"] * 100
    return [
        {
            "type": str(row.type),
            "total": int(row.total),
            "fraud": int(row.fraud),
            "fraud_rate": round(float(row.fraud_rate), 4),
        }
        for row in grouped.sort_values("type").itertuples(index=False)
    ]


@app.get("/api/charts/fraud-by-hour")
def chart_fraud_by_hour() -> list[dict[str, Any]]:
    dataset = _require_dataset()
    if not {"step", "isFraud"}.issubset(dataset.columns):
        raise HTTPException(503, "Dataset cannot produce the hourly fraud chart.")

    chart_data = dataset.assign(hour=dataset["step"] % 24).groupby("hour")["isFraud"].agg(
        total="count", fraud="sum"
    ).reset_index()
    chart_data["fraud_rate"] = chart_data["fraud"] / chart_data["total"] * 100
    return [
        {
            "hour": int(row.hour),
            "total": int(row.total),
            "fraud": int(row.fraud),
            "fraud_rate": round(float(row.fraud_rate), 4),
        }
        for row in chart_data.sort_values("hour").itertuples(index=False)
    ]


@app.get("/api/charts/amount-distribution")
def chart_amount_distribution() -> dict[str, Any]:
    """Label-separated amount quartiles, clipped only for display robustness."""
    dataset = _require_dataset()
    if not {"amount", "isFraud"}.issubset(dataset.columns):
        raise HTTPException(503, "Dataset cannot produce the amount-distribution chart.")

    cap = float(dataset["amount"].quantile(0.99))

    def quartiles(values: pd.Series) -> dict[str, float]:
        clipped = values[values <= cap]
        return {
            "min": round(float(clipped.min()), 2),
            "q1": round(float(clipped.quantile(0.25)), 2),
            "median": round(float(clipped.median()), 2),
            "q3": round(float(clipped.quantile(0.75)), 2),
            "max": round(float(clipped.max()), 2),
            "mean": round(float(clipped.mean()), 2),
        }

    return {
        "display_cap": round(cap, 2),
        "legitimate": quartiles(dataset.loc[dataset["isFraud"] == 0, "amount"]),
        "fraud": quartiles(dataset.loc[dataset["isFraud"] == 1, "amount"]),
    }


@app.get("/api/performance")
def model_performance() -> dict[str, Any]:
    """Evaluate the saved winner on the deterministic untouched test split."""
    model, preprocessor = _require_inference_artifacts()
    dataset = _require_dataset()
    if "isFraud" not in dataset.columns:
        raise HTTPException(503, "Dataset is missing its isFraud target column.")

    # Artifact format v2 records the outer split beneath ``evaluation``;
    # retain the old top-level fallback for previously trained artifacts.
    evaluation_metadata = _META.get("evaluation", {})
    split = evaluation_metadata.get("outer_holdout", _META.get("split", {}))
    test_size = float(split.get("test_size", 0.2))
    random_state = int(evaluation_metadata.get("random_state", split.get("random_state", 42)))
    raw = _raw_features(dataset)
    target = dataset["isFraud"]
    _, test_data, _, test_target = train_test_split(
        raw,
        target,
        test_size=test_size,
        stratify=target,
        random_state=random_state,
    )

    try:
        test_processed = preprocessor.transform(test_data)
        probabilities = _fraud_probabilities(model, test_processed)
    except Exception as exc:
        raise HTTPException(503, f"Saved artifacts cannot evaluate the test split: {exc}") from exc

    threshold = float(_META.get("prediction_threshold", 0.5))
    predicted = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(test_target, predicted, labels=[0, 1]).ravel()
    false_positive_rate, true_positive_rate, _ = roc_curve(test_target, probabilities)
    roc_auc = float(auc(false_positive_rate, true_positive_rate))

    # Keep a compact response while retaining the curve's shape for Recharts.
    step = max(1, len(false_positive_rate) // 200)
    roc_data = [
        {"fpr": round(float(fpr), 5), "tpr": round(float(tpr), 5)}
        for fpr, tpr in zip(false_positive_rate[::step], true_positive_rate[::step])
    ]
    if roc_data[-1] != {"fpr": 1.0, "tpr": 1.0}:
        roc_data.append({"fpr": 1.0, "tpr": 1.0})

    fpr_val = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    pr_auc_val = float(average_precision_score(test_target, probabilities))

    return {
        "metrics": {
            "accuracy": round(float(accuracy_score(test_target, predicted)), 4),
            "precision": round(float(precision_score(test_target, predicted, zero_division=0)), 4),
            "recall": round(float(recall_score(test_target, predicted, zero_division=0)), 4),
            "f1": round(float(f1_score(test_target, predicted, zero_division=0)), 4),
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc_val, 4),
            "false_positive_rate": round(fpr_val, 4),
        },
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "roc_curve": roc_data,
        "feature_importances": _feature_importance_data(model),
        "model_comparison": _META.get("comparison", []),
        "best_model_name": _META.get("best_model_name", "Unknown"),
        "selection_rationale": _META.get("selection_rationale", "Not recorded."),
        "evaluation_note": _dataset_info().get("validation_note", ""),
        "bootstrap_ci": _META.get("evaluation", {}).get("final_holdout_bootstrap_ci"),
    }


@app.post("/api/analyse-csv")
async def analyse_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    """Return basic EDA for a user-provided CSV; it never modifies training data."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(413, "CSV is too large. The limit is 20 MB.")

    try:
        uploaded = pd.read_csv(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse this CSV: {exc}") from exc

    result: dict[str, Any] = {
        "rows": int(len(uploaded)),
        "columns": list(uploaded.columns),
        "missing": int(uploaded.isnull().sum().sum()),
    }

    if "isFraud" in uploaded.columns:
        target = pd.to_numeric(uploaded["isFraud"], errors="coerce")
        if target.notna().any():
            result["fraud_rate"] = round(float(target.mean() * 100), 4)
            result["fraud_count"] = int(target.sum())

            if "type" in uploaded.columns:
                by_type = pd.DataFrame({"type": uploaded["type"], "isFraud": target}).dropna()
                grouped = by_type.groupby("type")["isFraud"].agg(total="count", fraud="sum").reset_index()
                grouped["fraud_rate"] = grouped["fraud"] / grouped["total"] * 100
                result["by_type"] = [
                    {
                        "type": str(row.type),
                        "total": int(row.total),
                        "fraud": int(row.fraud),
                        "fraud_rate": round(float(row.fraud_rate), 4),
                    }
                    for row in grouped.itertuples(index=False)
                ]

            if "amount" in uploaded.columns:
                amounts = pd.to_numeric(uploaded["amount"], errors="coerce")

                def amount_summary(mask: pd.Series) -> dict[str, float]:
                    values = amounts[mask & amounts.notna()]
                    if values.empty:
                        return {"mean": 0.0, "median": 0.0}
                    return {
                        "mean": round(float(values.mean()), 2),
                        "median": round(float(values.median()), 2),
                    }

                result["amount_stats"] = {
                    "legit": amount_summary(target == 0),
                    "fraud": amount_summary(target == 1),
                }

    return result


@app.get("/api/warmup")
def warmup() -> dict[str, Any]:
    """Warm up model artifacts and run a dummy scoring pass."""
    _load_artifacts()
    model, preprocessor = _require_inference_artifacts()
    dummy_input = pd.DataFrame(
        [
            {
                "step": 12,
                "type": "PAYMENT",
                "amount": 100.0,
                "oldbalanceOrg": 500.0,
                "newbalanceOrig": 400.0,
                "oldbalanceDest": 0.0,
                "newbalanceDest": 0.0,
            }
        ]
    )
    transformed = preprocessor.transform(_raw_features(dummy_input))
    prob = float(_fraud_probabilities(model, transformed)[0])
    return {"status": "warm", "dummy_probability": round(prob, 4)}


# Mount gateway and admin routers safely
try:
    from api.gateway import router as gateway_router  # noqa: E402
    app.include_router(gateway_router)
except Exception as _gw_exc:
    warnings.warn(f"Gateway router disabled: {_gw_exc}")

try:
    from api.admin import router as admin_router      # noqa: E402
    app.include_router(admin_router)
except Exception as _adm_exc:
    warnings.warn(f"Admin router disabled: {_adm_exc}")

