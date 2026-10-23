"""Reusable, inference-safe preprocessing for the fraud-detection prototype.

The bundled ``data/transactions.csv`` is a **synthetic PaySim-like development
fixture**, generated locally by ``generate_data.py``.  It is not a UPI/NPCI
transaction log.  This module deliberately keeps the input contract small and
explicit so that the same fitted object can be used during training and API
inference:

``step, type, amount, oldbalanceOrg, newbalanceOrig, oldbalanceDest,
newbalanceDest``.

Feature engineering lives *inside* the fitted sklearn pipeline.  In
particular, the high-value amount threshold is learned from the training split
only and then reused unchanged for validation, holdout evaluation, and API
requests.  Computing that threshold over the whole dataset before splitting
would leak information from the holdout set into training.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted


# Paths are relative to the repository root when scripts are run as documented.
DATA_PATH = Path("data/transactions.csv")
MODELS_DIR = Path("models")

TARGET_COLUMN = "isFraud"

# This is the only schema accepted by the saved preprocessor at inference time.
# Account IDs are intentionally excluded: they are high-cardinality identifiers
# that would encourage memorisation rather than generalisable fraud signals.
RAW_FEATURE_COLUMNS: tuple[str, ...] = (
    "step",
    "type",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
)

NUMERIC_RAW_FEATURE_COLUMNS: tuple[str, ...] = (
    "step",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
)
CATEGORICAL_RAW_FEATURE_COLUMNS: tuple[str, ...] = ("type",)

# Columns after deterministic feature engineering and before scaling / encoding.
ENGINEERED_NUMERIC_FEATURE_COLUMNS: tuple[str, ...] = (
    "step",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "hour_of_day",
    "is_high_value",
    "errorBalanceOrig",
    "errorBalanceDest",
)
ENGINEERED_CATEGORICAL_FEATURE_COLUMNS: tuple[str, ...] = ("type",)
ENGINEERED_FEATURE_COLUMNS: tuple[str, ...] = (
    *ENGINEERED_NUMERIC_FEATURE_COLUMNS,
    *ENGINEERED_CATEGORICAL_FEATURE_COLUMNS,
)

# Money/balance values have long right tails in PaySim-style data.  A signed
# log transform keeps a large positive or negative balance mismatch from
# dominating a linear baseline's optimisation while preserving its direction.
LOG_SCALED_FEATURE_COLUMNS: tuple[str, ...] = (
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "errorBalanceOrig",
    "errorBalanceDest",
)
LINEAR_SCALED_FEATURE_COLUMNS: tuple[str, ...] = ("step", "hour_of_day")
BINARY_FEATURE_COLUMNS: tuple[str, ...] = ("is_high_value",)

DEFAULT_HIGH_VALUE_QUANTILE = 0.95
KNOWN_SYNTHETIC_FIXTURE_SHA256 = (
    "49f15c888e3a68951e7cc69e22fc4c0814b994fc75de72a7d8aa0164cebba83a"
)



def _as_path(path: Path | str) -> Path:
    """Return a ``Path`` while keeping public function signatures flexible."""
    return path if isinstance(path, Path) else Path(path)


def _file_sha256(path: Path) -> str:
    """Calculate a content hash without loading the entire file into memory."""
    digest = sha256()
    with path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def signed_log1p(values: Any) -> np.ndarray:
    """Apply ``sign(x) * log(1 + abs(x))`` to numeric matrix-like input.

    The function is module-level so a fitted sklearn pipeline containing it is
    safely serialisable with joblib.  It handles balance-mismatch values that
    can be negative while retaining the original signal direction.
    """
    array = np.asarray(values, dtype=float)
    return np.sign(array) * np.log1p(np.abs(array))


def _require_columns(frame: pd.DataFrame, required_columns: Sequence[str], *, context: str) -> None:
    """Raise a useful error when a source frame misses required columns."""
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{context} is missing required column(s): {missing}. "
            f"Expected at least: {list(required_columns)}"
        )


def validate_transaction_frame(
    data: pd.DataFrame,
    *,
    require_target: bool = False,
    context: str = "Transaction data",
) -> pd.DataFrame:
    """Validate and normalise the raw PaySim-style input contract.

    The function never changes a fraud label's meaning: when ``require_target``
    is true it only verifies that ``isFraud`` is binary and preserves it as
    integer 0/1.  Extra columns (for example account IDs) are allowed but are
    ignored by the fitted preprocessing pipeline.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError(f"{context} must be a pandas DataFrame, not {type(data).__name__}.")
    if data.empty:
        raise ValueError(f"{context} is empty; at least one transaction is required.")
    if data.columns.duplicated().any():
        duplicates = data.columns[data.columns.duplicated()].tolist()
        raise ValueError(f"{context} has duplicate column names: {duplicates}.")

    expected = list(RAW_FEATURE_COLUMNS)
    if require_target:
        expected.append(TARGET_COLUMN)
    _require_columns(data, expected, context=context)

    # Work on a copy so callers retain their original DataFrame and labels.
    frame = data.copy()

    for column in NUMERIC_RAW_FEATURE_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        values_as_array = values.to_numpy(dtype=float, na_value=np.nan)
        invalid = values.isna() | ~np.isfinite(values_as_array)
        if bool(np.any(invalid)):
            raise ValueError(
                f"{context} column '{column}' contains null, non-numeric, or non-finite values."
            )
        if column == "amount" and bool((values <= 0).any()):
            raise ValueError(f"{context} column 'amount' must be strictly positive.")
        if column != "amount" and bool((values < 0).any()):
            raise ValueError(f"{context} column '{column}' cannot contain negative values.")
        frame[column] = values.astype(float)

    # Transaction types are normalised consistently.  Unknown categories are
    # rejected later by the fitted transformer rather than silently encoded as
    # all-zero vectors, which makes input mistakes visible to API callers.
    if frame["type"].isna().any():
        raise ValueError(f"{context} column 'type' contains null values.")
    transaction_types = frame["type"].astype("string").str.strip().str.upper()
    if transaction_types.isna().any() or bool((transaction_types == "").any()):
        raise ValueError(f"{context} column 'type' contains empty values.")
    frame["type"] = transaction_types.astype(str)

    if require_target:
        target = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
        target_as_array = target.to_numpy(dtype=float, na_value=np.nan)
        invalid_target = (
            target.isna()
            | ~np.isfinite(target_as_array)
            | ~target.isin([0, 1])
        )
        if bool(np.any(invalid_target)):
            raise ValueError(
                f"{context} column '{TARGET_COLUMN}' must contain only binary 0/1 labels. "
                "Labels are not inferred or rewritten by this project."
            )
        frame[TARGET_COLUMN] = target.astype(np.int8)

    return frame


def _validate_training_class_distribution(target: pd.Series) -> None:
    """Ensure that stratified split + SMOTE are mathematically possible."""
    counts = target.value_counts().sort_index()
    if set(counts.index.tolist()) != {0, 1}:
        raise ValueError(
            f"'{TARGET_COLUMN}' must contain both legitimate (0) and fraud (1) labels; "
            f"observed counts: {counts.to_dict()}."
        )
    # The later outer split and inner validation split both need positive
    # examples.  Six is a deliberately conservative lower bound; datasets
    # smaller than this need a different evaluation design rather than a
    # misleading SMOTE result.
    if int(counts.min()) < 6:
        raise ValueError(
            "At least 6 examples of each class are required for the configured "
            "stratified train/validation/test workflow."
        )


def infer_dataset_provenance(
    path: Path | str,
    frame: pd.DataFrame,
    *,
    declared_source: Optional[str] = None,
    declared_kind: str = "auto",
) -> dict[str, Any]:
    """Create transparent dataset provenance for model metadata.

    The checked-in fixture is recognised by its SHA-256 fingerprint.  A file
    replacement is therefore *not* silently claimed to be synthetic.  For a
    replacement dataset, pass a source description and ``declared_kind`` of
    ``synthetic``, ``public``, or ``unknown`` from ``train_model.py``.
    """
    dataset_path = _as_path(path)
    if declared_kind not in {"auto", "synthetic", "public", "unknown"}:
        raise ValueError(
            "declared_kind must be one of: auto, synthetic, public, unknown."
        )

    fingerprint = _file_sha256(dataset_path)
    base: dict[str, Any] = {
        "path": str(dataset_path),
        "sha256": fingerprint,
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "target_column": TARGET_COLUMN,
        "class_counts": {
            str(label): int(count)
            for label, count in frame[TARGET_COLUMN].value_counts().sort_index().items()
        },
        "fraud_rate": float(frame[TARGET_COLUMN].mean()),
        "duplicate_row_count": int(frame.duplicated().sum()),
        "evaluation_caveat": (
            "This holdout evaluation is for a development dataset only. It is not "
            "evidence of performance on real UPI/NPCI traffic, and it is not a "
            "substitute for external validation on a documented public dataset."
        ),
        "validation_note": (
            "Development-only evaluation. Do not present these metrics as validation "
            "against real UPI/NPCI transactions or production fraud traffic."
        ),
    }

    if declared_kind != "auto":
        base.update(
            {
                "source_classification": f"user_declared_{declared_kind}",
                "source_description": declared_source or "User-declared dataset source.",
                "source": declared_source or "User-declared dataset source.",
                "is_synthetic": True if declared_kind == "synthetic" else False if declared_kind == "public" else None,
                "real_upi_network_data": False if declared_kind in {"synthetic", "public"} else None,
                "provenance_confidence": "user-declared",
            }
        )
        return base

    # Current project fixture: generated deterministically by generate_data.py
    # and deliberately labelled as synthetic.  The fingerprint prevents that
    # claim from following a user-supplied replacement file automatically.
    if fingerprint == KNOWN_SYNTHETIC_FIXTURE_SHA256:
        base.update(
            {
                "source_classification": "project_local_synthetic_fixture",
                "source_description": (
                    "Project-local synthetic PaySim-like development fixture generated "
                    "by generate_data.py; it is not a public bank, NPCI, or live UPI dataset."
                ),
                "source": (
                    "Synthetic/generated PaySim-like development fixture from the "
                    "project-local generate_data.py script (not UPI/NPCI data)."
                ),
                "is_synthetic": True,
                "real_upi_network_data": False,
                "provenance_confidence": "fixture fingerprint matched",
            }
        )
    else:
        base.update(
            {
                "source_classification": "unverified_replacement_dataset",
                "source_description": (
                    declared_source
                    or "Dataset provenance was not declared. The project-local synthetic "
                    "fixture fingerprint did not match this file."
                ),
                "source": (
                    declared_source
                    or "Unverified replacement dataset; provenance was not declared."
                ),
                "is_synthetic": None,
                "real_upi_network_data": None,
                "provenance_confidence": "unverified",
            }
        )
    return base


def load_and_validate_dataset(
    path: Path | str = DATA_PATH,
    *,
    declared_source: Optional[str] = None,
    declared_kind: str = "auto",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load labelled CSV data, validate it, and return provenance metadata."""
    dataset_path = _as_path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path.resolve()}")

    try:
        raw_frame = pd.read_csv(dataset_path)
    except Exception as error:  # pragma: no cover - exact parser failures vary
        raise ValueError(f"Could not read CSV dataset '{dataset_path}': {error}") from error

    frame = validate_transaction_frame(
        raw_frame,
        require_target=True,
        context=f"Dataset '{dataset_path}'",
    )
    _validate_training_class_distribution(frame[TARGET_COLUMN])
    provenance = infer_dataset_provenance(
        dataset_path,
        frame,
        declared_source=declared_source,
        declared_kind=declared_kind,
    )
    return frame, provenance


class PaySimFeatureEngineer(BaseEstimator, TransformerMixin):
    """Fit leakage-safe deterministic features from raw PaySim-style columns.

    ``high_value_threshold_`` is estimated during :meth:`fit` from the amount
    column of whichever training partition is supplied.  :meth:`transform`
    never recalculates it.  That property is why serialising the complete
    pipeline is safer than reproducing feature formulas separately in an API.
    """

    def __init__(self, high_value_quantile: float = DEFAULT_HIGH_VALUE_QUANTILE):
        self.high_value_quantile = high_value_quantile

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        if not 0 < self.high_value_quantile < 1:
            raise ValueError("high_value_quantile must be strictly between 0 and 1.")

        frame = validate_transaction_frame(X, context="Preprocessor fit input")
        self.raw_feature_columns_ = np.asarray(RAW_FEATURE_COLUMNS, dtype=object)
        self.transaction_types_ = tuple(sorted(frame["type"].unique().tolist()))
        self.high_value_threshold_ = float(
            frame["amount"].quantile(self.high_value_quantile)
        )
        if not np.isfinite(self.high_value_threshold_):
            raise ValueError("Could not calculate a finite high-value threshold from training amounts.")
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(
            self,
            attributes=["raw_feature_columns_", "transaction_types_", "high_value_threshold_"],
        )
        frame = validate_transaction_frame(X, context="Preprocessor transform input")

        unseen_types = sorted(set(frame["type"].unique()) - set(self.transaction_types_))
        if unseen_types:
            raise ValueError(
                "Unknown transaction type(s) for this fitted model: "
                f"{unseen_types}. Accepted types: {list(self.transaction_types_)}."
            )

        engineered = pd.DataFrame(index=frame.index)
        for column in NUMERIC_RAW_FEATURE_COLUMNS:
            engineered[column] = frame[column]

        # ``step`` is an hourly counter in PaySim-style data.  The modulo
        # derivation is deterministic and does not look at target labels.
        engineered["hour_of_day"] = frame["step"] % 24
        engineered["is_high_value"] = (
            frame["amount"] > self.high_value_threshold_
        ).astype(np.int8)

        # Balance mismatch is zero when the recorded balance changes exactly
        # by the transaction amount.  It is a useful behavioural signal, not a
        # target-derived value.
        engineered["errorBalanceOrig"] = (
            frame["newbalanceOrig"] + frame["amount"] - frame["oldbalanceOrg"]
        )
        engineered["errorBalanceDest"] = (
            frame["oldbalanceDest"] + frame["amount"] - frame["newbalanceDest"]
        )
        engineered["type"] = frame["type"]

        return engineered.loc[:, list(ENGINEERED_FEATURE_COLUMNS)]

    def get_feature_names_out(self, input_features: Optional[Iterable[str]] = None) -> np.ndarray:
        """Expose engineered column names to sklearn's downstream pipeline."""
        return np.asarray(ENGINEERED_FEATURE_COLUMNS, dtype=object)


def build_preprocessor(
    high_value_quantile: float = DEFAULT_HIGH_VALUE_QUANTILE,
) -> Pipeline:
    """Build an unfitted pipeline that accepts raw transaction base columns.

    Calling ``fit`` on this pipeline learns both the amount threshold and the
    scaler/encoder parameters from the supplied training partition only.
    """
    log_numeric_pipeline = Pipeline(
        steps=[
            ("signed_log1p", FunctionTransformer(signed_log1p, feature_names_out="one-to-one")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]
    )
    column_preprocessor = ColumnTransformer(
        transformers=[
            ("log_numeric", log_numeric_pipeline, list(LOG_SCALED_FEATURE_COLUMNS)),
            ("linear_numeric", StandardScaler(), list(LINEAR_SCALED_FEATURE_COLUMNS)),
            ("binary", "passthrough", list(BINARY_FEATURE_COLUMNS)),
            ("categorical", categorical_pipeline, list(ENGINEERED_CATEGORICAL_FEATURE_COLUMNS)),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline(
        steps=[
            ("feature_engineering", PaySimFeatureEngineer(high_value_quantile)),
            ("column_preprocessing", column_preprocessor),
        ]
    )


def get_feature_names(preprocessor: Pipeline) -> list[str]:
    """Return the final model feature names after one-hot encoding."""
    check_is_fitted(preprocessor)
    return [str(name) for name in preprocessor.get_feature_names_out().tolist()]


def get_high_value_threshold(preprocessor: Pipeline) -> float:
    """Read the train-fitted high-value threshold from a saved pipeline."""
    feature_engineering = preprocessor.named_steps.get("feature_engineering")
    if feature_engineering is None:
        raise ValueError("Expected a pipeline with a 'feature_engineering' step.")
    check_is_fitted(feature_engineering, attributes=["high_value_threshold_"])
    return float(feature_engineering.high_value_threshold_)


def get_preprocessor_contract(preprocessor: Pipeline) -> dict[str, Any]:
    """Return JSON-safe schema details for API/frontend metadata."""
    feature_engineering = preprocessor.named_steps.get("feature_engineering")
    if feature_engineering is None:
        raise ValueError("Expected a pipeline with a 'feature_engineering' step.")
    check_is_fitted(feature_engineering, attributes=["transaction_types_"])
    return {
        "raw_feature_columns": list(RAW_FEATURE_COLUMNS),
        "raw_numeric_feature_columns": list(NUMERIC_RAW_FEATURE_COLUMNS),
        "raw_categorical_feature_columns": list(CATEGORICAL_RAW_FEATURE_COLUMNS),
        "derived_feature_columns": list(ENGINEERED_FEATURE_COLUMNS),
        "numeric_transformations": {
            "signed_log1p_then_standard_scale": list(LOG_SCALED_FEATURE_COLUMNS),
            "standard_scale": list(LINEAR_SCALED_FEATURE_COLUMNS),
            "passthrough_binary": list(BINARY_FEATURE_COLUMNS),
        },
        "model_feature_names": get_feature_names(preprocessor),
        "accepted_transaction_types": list(feature_engineering.transaction_types_),
        "high_value_quantile": float(feature_engineering.high_value_quantile),
        "high_value_threshold": get_high_value_threshold(preprocessor),
        "unknown_transaction_type_policy": "reject before one-hot encoding",
    }


def get_raw_features_and_target(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Select raw model inputs and untouched binary labels from validated data."""
    _require_columns(frame, [*RAW_FEATURE_COLUMNS, TARGET_COLUMN], context="Validated dataset")
    return frame.loc[:, list(RAW_FEATURE_COLUMNS)].copy(), frame[TARGET_COLUMN].copy()


def load_and_engineer(path: Path | str = DATA_PATH) -> pd.DataFrame:
    """Return deterministic EDA-friendly features without fitting a threshold.

    This compatibility helper exists for the legacy Streamlit dashboard.  It
    does **not** add ``is_high_value`` because that feature requires the
    train-fitted threshold held in :func:`build_preprocessor`.  Training and
    inference must use the saved preprocessor directly.
    """
    frame, _ = load_and_validate_dataset(path)
    result = frame.copy()
    result["hour_of_day"] = result["step"] % 24
    result["errorBalanceOrig"] = (
        result["newbalanceOrig"] + result["amount"] - result["oldbalanceOrg"]
    )
    result["errorBalanceDest"] = (
        result["oldbalanceDest"] + result["amount"] - result["newbalanceDest"]
    )
    return result


def get_train_test_splits(
    path: Path | str = DATA_PATH,
    *,
    random_state: int = 42,
    test_size: float = 0.20,
) -> tuple[np.ndarray, np.ndarray, pd.Series, pd.Series, Pipeline, list[str]]:
    """Compatibility helper for a simple leakage-safe stratified split.

    The training script uses a stricter nested development/validation/holdout
    workflow for model selection.  This helper remains useful for a notebook
    and, crucially, still fits all preprocessing only on the training side.
    """
    if not 0 < test_size < 1:
        raise ValueError("test_size must be between 0 and 1.")
    frame, _ = load_and_validate_dataset(path)
    X_raw, y = get_raw_features_and_target(frame)
    X_train, X_test, y_train, y_test = train_test_split(
        X_raw,
        y,
        test_size=test_size,
        stratify=y,
        random_state=random_state,
    )
    preprocessor = build_preprocessor()
    X_train_processed = preprocessor.fit_transform(X_train, y_train)
    X_test_processed = preprocessor.transform(X_test)
    return (
        X_train_processed,
        X_test_processed,
        y_train,
        y_test,
        preprocessor,
        get_feature_names(preprocessor),
    )


if __name__ == "__main__":
    # A lightweight manual smoke test.  Use train_model.py to create artifacts.
    X_train, X_test, y_train, y_test, fitted, feature_names = get_train_test_splits()
    print(f"Train shape: {X_train.shape} | Test shape: {X_test.shape}")
    print(f"Fraud in train: {int(y_train.sum())} | Fraud in test: {int(y_test.sum())}")
    print(f"High-value threshold fitted on train: {get_high_value_threshold(fitted):.2f}")
    print(f"Model feature names ({len(feature_names)}): {feature_names}")
