"""Train and evaluate the Milestone 1 fraud-classification models.

This script is intentionally conservative about evaluation:

1. The labelled CSV is validated without inventing or changing fraud labels.
2. A stratified 80/20 holdout is reserved before model selection.
3. The development partition is split again into training/validation data.
4. Every fitted transformation and SMOTENC operation sees training rows only.
5. Model choice uses validation metrics; the untouched holdout is used once for
   the final selected model.

The current bundled file is a locally generated synthetic PaySim-like fixture,
not real UPI/NPCI data.  Its evaluation results are therefore development
evidence only, not a claim of production fraud-detection performance.

Run from the repository root:

    .venv/bin/python src/train_model.py

For a replacement dataset, declare its provenance rather than inheriting the
synthetic-fixture label:

    .venv/bin/python src/train_model.py --data path/to/data.csv \
      --dataset-kind public --dataset-source "Kaggle: <dataset name and URL>"
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Joblib's macOS physical-core probe can fail in restricted desktop shells and
# print a noisy stack trace from worker processes.  This only scopes joblib's
# worker-count discovery; it does not alter the host system configuration.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTENC
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# imbalanced-learn 0.12 emits this compatibility warning with sklearn 1.6.
# It is third-party-library noise, not a warning about the dataset or model.
warnings.filterwarnings(
    "ignore",
    message="`BaseEstimator._check_(n_features|feature_names)` is deprecated",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    message="Could not find the number of physical cores.*",
    category=UserWarning,
)

# Allow ``python src/train_model.py`` while still importing from the package.
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.preprocessing import (  # noqa: E402
    DATA_PATH,
    MODELS_DIR,
    NUMERIC_RAW_FEATURE_COLUMNS,
    RAW_FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_preprocessor,
    get_feature_names,
    get_preprocessor_contract,
    get_raw_features_and_target,
    load_and_validate_dataset,
)


RANDOM_STATE = 42
OUTER_TEST_SIZE = 0.20
# 25% of the 80% development partition => 20% of the full dataset.
VALIDATION_SIZE_OF_DEVELOPMENT = 0.25
OPERATING_THRESHOLD = 0.50
DEFAULT_SMOTE_K_NEIGHBORS = 5


def _class_counts(target: pd.Series | np.ndarray) -> dict[str, int]:
    """Return JSON-safe binary class counts with stable 0/1 keys."""
    series = pd.Series(target)
    return {str(label): int(count) for label, count in series.value_counts().sort_index().items()}


def _model_factories(random_state: int) -> dict[str, Callable[[], Any]]:
    """Return portable model factories for a genuine three-model comparison.

    XGBoost is optional in the project guide and is intentionally not required
    here: the local macOS environment lacks its OpenMP runtime.  Histogram
    Gradient Boosting provides a third, fully scikit-learn, portable model.
    Class weights are not also applied because the training partitions are
    balanced by SMOTENC; using both would double-correct the class imbalance.
    """
    return {
        "Logistic Regression": lambda: LogisticRegression(
            max_iter=2_000,
            # liblinear remains numerically stable on this deliberately
            # separable synthetic fixture; L-BFGS emits overflow warnings here.
            solver="liblinear",
            C=0.1,
            random_state=random_state,
        ),
        "Random Forest": lambda: RandomForestClassifier(
            n_estimators=250,
            max_depth=14,
            min_samples_leaf=2,
            random_state=random_state,
            # One worker keeps local/CI output deterministic and avoids an
            # OS-specific physical-core discovery warning from joblib.
            n_jobs=1,
        ),
        "Histogram Gradient Boosting": lambda: HistGradientBoostingClassifier(
            learning_rate=0.08,
            max_iter=250,
            max_leaf_nodes=31,
            l2_regularization=0.001,
            random_state=random_state,
        ),
    }


def _model_config_summary() -> dict[str, dict[str, Any]]:
    """Small human-readable configs suitable for metadata, not raw estimator dumps."""
    return {
        "Logistic Regression": {
            "family": "linear baseline",
            "max_iter": 2000,
            "solver": "liblinear",
            "C": 0.1,
        },
        "Random Forest": {
            "family": "bagged decision-tree ensemble",
            "n_estimators": 250,
            "max_depth": 14,
            "min_samples_leaf": 2,
        },
        "Histogram Gradient Boosting": {
            "family": "gradient-boosted decision trees",
            "learning_rate": 0.08,
            "max_iter": 250,
            "max_leaf_nodes": 31,
            "l2_regularization": 0.001,
        },
    }


def _compatible_smote_k_neighbors(target: pd.Series | np.ndarray) -> int:
    """Choose a valid SMOTE neighbor count for the current training partition."""
    counts = pd.Series(target).value_counts()
    minority_count = int(counts.min())
    if minority_count < 2:
        raise ValueError(
            "SMOTENC needs at least two minority examples in the training partition."
        )
    return min(DEFAULT_SMOTE_K_NEIGHBORS, minority_count - 1)


def resample_training_raw_features(
    X_train_raw: pd.DataFrame,
    y_train: pd.Series,
    *,
    random_state: int,
) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    """Apply SMOTENC only to a training partition and return raw synthetic rows.

    Numerical raw fields are standardised *for the neighbour-distance search*
    so a high-variance balance field does not dominate ``step`` or amount.  The
    result is inverse-scaled back to raw units before the saved inference
    preprocessor engineers/scales/encodes it.  ``type`` is explicitly marked
    categorical, so SMOTENC does not interpolate values such as ``CASH_OUT``.
    """
    raw = X_train_raw.loc[:, list(RAW_FEATURE_COLUMNS)].copy()
    before_counts = _class_counts(y_train)
    k_neighbors = _compatible_smote_k_neighbors(y_train)

    neighbour_scaler = StandardScaler()
    smote_input = raw.copy()
    smote_input.loc[:, list(NUMERIC_RAW_FEATURE_COLUMNS)] = neighbour_scaler.fit_transform(
        raw.loc[:, list(NUMERIC_RAW_FEATURE_COLUMNS)]
    )

    type_column_index = list(RAW_FEATURE_COLUMNS).index("type")
    smote = SMOTENC(
        categorical_features=[type_column_index],
        random_state=random_state,
        k_neighbors=k_neighbors,
    )
    X_resampled_scaled, y_resampled = smote.fit_resample(smote_input, y_train)

    # imbalanced-learn preserves a DataFrame here, but retaining this conversion
    # makes the data contract explicit across supported package versions.
    if not isinstance(X_resampled_scaled, pd.DataFrame):
        X_resampled_scaled = pd.DataFrame(
            X_resampled_scaled,
            columns=list(RAW_FEATURE_COLUMNS),
        )
    X_resampled_raw = X_resampled_scaled.loc[:, list(RAW_FEATURE_COLUMNS)].copy()
    X_resampled_raw.loc[:, list(NUMERIC_RAW_FEATURE_COLUMNS)] = neighbour_scaler.inverse_transform(
        X_resampled_raw.loc[:, list(NUMERIC_RAW_FEATURE_COLUMNS)]
    )
    X_resampled_raw["type"] = X_resampled_raw["type"].astype(str)

    # The interpolation is a convex combination of valid non-negative inputs,
    # but validate again so a package change cannot silently create bad rows.
    from src.preprocessing import validate_transaction_frame  # local import avoids a long import list

    X_resampled_raw = validate_transaction_frame(
        X_resampled_raw,
        context="SMOTENC training output",
    ).loc[:, list(RAW_FEATURE_COLUMNS)]
    y_resampled = pd.Series(y_resampled, name=TARGET_COLUMN).astype(np.int8)

    metadata = {
        "method": "SMOTENC",
        "applied_to": "training partition only",
        "categorical_raw_columns": ["type"],
        "numeric_distance_scaling": "StandardScaler fitted on the same training partition only",
        "k_neighbors": int(k_neighbors),
        "class_counts_before": before_counts,
        "class_counts_after": _class_counts(y_resampled),
    }
    return X_resampled_raw, y_resampled, metadata


def _metric_record(
    name: str,
    model: Any,
    X_evaluation: np.ndarray,
    y_evaluation: pd.Series,
    *,
    split_name: str,
) -> dict[str, Any]:
    """Evaluate a fitted model using fraud-relevant metrics at a fixed threshold."""
    # Some macOS Accelerate builds surface a spurious floating-point status
    # warning for otherwise finite dense matrix products during predict_proba.
    # We suppress only that low-level warning and immediately assert that the
    # resulting probabilities are finite, so genuine numerical failures still
    # stop the run rather than being hidden.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*encountered in matmul",
            category=RuntimeWarning,
        )
        probabilities = model.predict_proba(X_evaluation)[:, 1]
    if not np.isfinite(probabilities).all():
        raise ValueError(f"{name} produced non-finite fraud probabilities on {split_name}.")
    predictions = (probabilities >= OPERATING_THRESHOLD).astype(np.int8)
    tn, fp, fn, tp = confusion_matrix(y_evaluation, predictions, labels=[0, 1]).ravel()

    # Keep full precision while selecting the model; JSON table values are
    # rounded only for readability once the record is constructed.
    precision = float(precision_score(y_evaluation, predictions, zero_division=0))
    recall = float(recall_score(y_evaluation, predictions, zero_division=0))
    f1 = float(f1_score(y_evaluation, predictions, zero_division=0))
    roc_auc = float(roc_auc_score(y_evaluation, probabilities))
    pr_auc = float(average_precision_score(y_evaluation, probabilities))
    accuracy = float(accuracy_score(y_evaluation, predictions))

    return {
        "Model": name,
        "Evaluation Split": split_name,
        "Operating Threshold": OPERATING_THRESHOLD,
        "Accuracy": round(accuracy, 6),
        "Precision": round(precision, 6),
        "Recall": round(recall, 6),
        "F1": round(f1, 6),
        "ROC-AUC": round(roc_auc, 6),
        "PR-AUC": round(pr_auc, 6),
        "Confusion Matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
        "Evaluation Class Counts": _class_counts(y_evaluation),
    }


def _selection_score(metrics: dict[str, Any]) -> float:
    """Recall-first score used on validation data only.

    Recall receives 60% of the score because missing true fraud is costly.
    F1 and PR-AUC make the decision less likely to select a model that obtains
    high recall solely by flagging every transaction.  PR-AUC is particularly
    informative for the heavily imbalanced fraud class.
    """
    return (
        0.60 * float(metrics["Recall"])
        + 0.25 * float(metrics["F1"])
        + 0.15 * float(metrics["PR-AUC"])
    )


def _add_selection_scores(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copies with a transparent validation-only selection score."""
    enriched: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        item["Selection Score"] = round(_selection_score(result), 6)
        enriched.append(item)
    return enriched


def _choose_best_model(results: list[dict[str, Any]]) -> str:
    """Choose using validation only, preferring the simpler model for exact ties."""
    if not results:
        raise ValueError("Cannot select a model from an empty result list.")
    simplicity_rank = {
        "Logistic Regression": 3,
        "Random Forest": 2,
        "Histogram Gradient Boosting": 1,
    }
    return max(
        results,
        key=lambda result: (
            _selection_score(result),
            float(result["Recall"]),
            float(result["F1"]),
            float(result["PR-AUC"]),
            float(result["ROC-AUC"]),
            simplicity_rank[result["Model"]],
        ),
    )["Model"]


def _print_metric_table(results: list[dict[str, Any]], *, heading: str) -> None:
    """Print a concise evidence table without leading with accuracy."""
    table = pd.DataFrame(results)
    columns = ["Model", "Recall", "Precision", "F1", "PR-AUC", "ROC-AUC", "Accuracy"]
    columns = [column for column in columns if column in table.columns]
    print(f"\n{'=' * 84}\n{heading}\n{'=' * 84}")
    print(table.loc[:, columns].to_string(index=False))


def _stratified_sample_for_importance(
    X: np.ndarray,
    y: pd.Series,
    *,
    max_rows: int = 10_000,
) -> tuple[np.ndarray, pd.Series]:
    """Cap expensive permutation importance while preserving the fraud ratio."""
    if len(y) <= max_rows:
        return X, y
    positions = np.arange(len(y))
    selected, _ = train_test_split(
        positions,
        train_size=max_rows,
        stratify=y,
        random_state=RANDOM_STATE,
    )
    return X[selected], y.iloc[selected].reset_index(drop=True)


def _feature_importance_table(
    model: Any,
    feature_names: list[str],
    X_holdout: np.ndarray,
    y_holdout: pd.Series,
) -> tuple[pd.DataFrame, str]:
    """Create a model-appropriate feature-importance table for the UI."""
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
        method = "native impurity-based feature importance"
    elif isinstance(model, LogisticRegression):
        values = np.abs(np.asarray(model.coef_).ravel())
        method = "absolute coefficient magnitude on preprocessed features"
    else:
        sample_X, sample_y = _stratified_sample_for_importance(X_holdout, y_holdout)
        importance = permutation_importance(
            model,
            sample_X,
            sample_y,
            scoring="average_precision",
            n_repeats=3,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        values = np.asarray(importance.importances_mean, dtype=float)
        method = "permutation importance (mean drop in average precision)"

    if len(values) != len(feature_names):
        raise ValueError(
            "Feature-importance length does not match the fitted preprocessing schema."
        )
    table = (
        pd.DataFrame({"feature": feature_names, "importance": values})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    return table, method


def _atomic_joblib_dump(value: Any, destination: Path) -> None:
    """Write a joblib artifact atomically so model/preprocessor pairs stay consistent."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
    try:
        joblib.dump(value, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _atomic_json_dump(value: dict[str, Any], destination: Path) -> None:
    """Write JSON metadata atomically and with stable human-readable formatting."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        json.dump(value, temporary_file, indent=2, sort_keys=False)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)
    try:
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _atomic_csv_dump(value: pd.DataFrame, destination: Path) -> None:
    """Write the feature-importance CSV atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        value.to_csv(temporary_file, index=False)
        temporary_path = Path(temporary_file.name)
    try:
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _split_raw_data(
    X_raw: pd.DataFrame,
    y: pd.Series,
    *,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Create an outer holdout and an inner validation split, all stratified."""
    X_development, X_holdout, y_development, y_holdout = train_test_split(
        X_raw,
        y,
        test_size=OUTER_TEST_SIZE,
        stratify=y,
        random_state=random_state,
    )
    X_selection_train, X_validation, y_selection_train, y_validation = train_test_split(
        X_development,
        y_development,
        test_size=VALIDATION_SIZE_OF_DEVELOPMENT,
        stratify=y_development,
        random_state=random_state,
    )
    return (
        X_development,
        X_holdout,
        y_development,
        y_holdout,
        X_selection_train,
        X_validation,
        y_selection_train,
        y_validation,
    )


def train(
    *,
    data_path: Path | str = DATA_PATH,
    dataset_source: str | None = None,
    dataset_kind: str = "auto",
    random_state: int = RANDOM_STATE,
) -> tuple[Any, pd.DataFrame, dict[str, Any]]:
    """Run the full leakage-safe training workflow and persist artifacts."""
    print("Loading and validating labelled transaction data…")
    frame, provenance = load_and_validate_dataset(
        data_path,
        declared_source=dataset_source,
        declared_kind=dataset_kind,
    )
    X_raw, y = get_raw_features_and_target(frame)
    print(
        f"Validated {len(frame):,} rows; class counts: {_class_counts(y)}; "
        f"provenance: {provenance['source_classification']}."
    )

    (
        X_development,
        X_holdout,
        y_development,
        y_holdout,
        X_selection_train,
        X_validation,
        y_selection_train,
        y_validation,
    ) = _split_raw_data(X_raw, y, random_state=random_state)

    # ── Model selection: train + validation only ─────────────────────────
    print("\nPreparing development training partition (preprocessing + SMOTENC)…")
    selection_preprocessor = build_preprocessor()
    selection_preprocessor.fit(X_selection_train, y_selection_train)
    X_selection_resampled_raw, y_selection_resampled, selection_smote_metadata = (
        resample_training_raw_features(
            X_selection_train,
            y_selection_train,
            random_state=random_state,
        )
    )
    X_selection_resampled = selection_preprocessor.transform(X_selection_resampled_raw)
    X_validation_processed = selection_preprocessor.transform(X_validation)

    factories = _model_factories(random_state)
    validation_results: list[dict[str, Any]] = []
    for model_name, factory in factories.items():
        print(f"Training {model_name} for validation selection…")
        candidate = factory()
        candidate.fit(X_selection_resampled, y_selection_resampled)
        validation_results.append(
            _metric_record(
                model_name,
                candidate,
                X_validation_processed,
                y_validation,
                split_name="validation (not holdout)",
            )
        )

    validation_results = _add_selection_scores(validation_results)
    _print_metric_table(validation_results, heading="MODEL SELECTION — STRATIFIED VALIDATION ONLY")
    best_model_name = _choose_best_model(validation_results)
    print(f"\nSelected model from validation only: {best_model_name}")

    # ── Final training + one untouched holdout evaluation ─────────────────
    # Fit a *new* pipeline on the complete development partition.  The outer
    # holdout has still never influenced a threshold, scaler, encoder, SMOTE
    # neighbour search, model parameter, or model-selection decision.
    print("\nRefitting selected model on the complete development partition…")
    final_preprocessor = build_preprocessor()
    final_preprocessor.fit(X_development, y_development)
    X_development_resampled_raw, y_development_resampled, final_smote_metadata = (
        resample_training_raw_features(
            X_development,
            y_development,
            random_state=random_state,
        )
    )
    X_development_resampled = final_preprocessor.transform(X_development_resampled_raw)
    X_holdout_processed = final_preprocessor.transform(X_holdout)

    final_model = factories[best_model_name]()
    final_model.fit(X_development_resampled, y_development_resampled)
    holdout_metrics = _metric_record(
        best_model_name,
        final_model,
        X_holdout_processed,
        y_holdout,
        split_name="untouched stratified holdout",
    )
    _print_metric_table([holdout_metrics], heading="FINAL SELECTED MODEL — UNTOUCHED HOLDOUT")

    feature_names = get_feature_names(final_preprocessor)
    feature_importance, importance_method = _feature_importance_table(
        final_model,
        feature_names,
        X_holdout_processed,
        y_holdout,
    )

    preprocessing_contract = get_preprocessor_contract(final_preprocessor)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    metadata: dict[str, Any] = {
        "artifact_format_version": 2,
        "trained_at_utc": now,
        "project_scope": {
            "title": "UPI Fraud Detection Using Machine Learning",
            "description": (
                "Transaction-level digital-payment fraud-classification prototype. "
                "It is not connected to the real UPI/NPCI network and is not "
                "real-time payment-network infrastructure."
            ),
        },
        "dataset_provenance": provenance,
        # ``dataset`` is retained as an alias for small consumers that look for
        # a short key; both point to the same JSON-safe information.
        "dataset": provenance,
        "target_column": TARGET_COLUMN,
        "raw_feature_columns": list(RAW_FEATURE_COLUMNS),
        "feature_names": feature_names,
        "high_value_threshold": preprocessing_contract["high_value_threshold"],
        "high_value_quantile": preprocessing_contract["high_value_quantile"],
        "preprocessing": {
            **preprocessing_contract,
            "artifact": "models/preprocessor.pkl",
            "inference_instruction": (
                "Pass a DataFrame containing raw_feature_columns to preprocessor.transform(). "
                "Do not recreate derived features or recalculate the high-value threshold in the API."
            ),
        },
        "model_artifact": "models/fraud_model.pkl",
        "best_model_name": best_model_name,
        "model_configurations": _model_config_summary(),
        "optional_xgboost": {
            "status": "not_run",
            "reason": (
                "XGBoost is optional. A portable scikit-learn gradient-boosting "
                "model was used for the third comparison model."
            ),
        },
        # Backward-compatible API/UI table: these are validation results, made
        # explicit so they are never presented as an independently selected test.
        "comparison": validation_results,
        "evaluation": {
            "random_state": random_state,
            "operating_threshold": OPERATING_THRESHOLD,
            "headline_metric_guidance": (
                "Accuracy is reported for completeness but must not be used as the "
                "headline metric on this imbalanced fraud dataset. Prioritise recall, "
                "precision, F1, PR-AUC, and ROC-AUC."
            ),
            "outer_holdout": {
                "strategy": "stratified train/test split",
                "test_size": OUTER_TEST_SIZE,
                "development_rows": int(len(X_development)),
                "holdout_rows": int(len(X_holdout)),
                "development_class_counts": _class_counts(y_development),
                "holdout_class_counts": _class_counts(y_holdout),
                "used_for_model_selection": False,
            },
            "model_selection_validation": {
                "strategy": "stratified split inside development partition",
                "validation_fraction_of_development": VALIDATION_SIZE_OF_DEVELOPMENT,
                "selection_train_rows": int(len(X_selection_train)),
                "validation_rows": int(len(X_validation)),
                "selection_train_class_counts": _class_counts(y_selection_train),
                "validation_class_counts": _class_counts(y_validation),
                "results": validation_results,
                "selection_score": (
                    "0.60 * Recall + 0.25 * F1 + 0.15 * PR-AUC; exact ties prefer "
                    "the simpler model."
                ),
            },
            "class_imbalance_strategy": {
                "selection_training": selection_smote_metadata,
                "final_development_training": final_smote_metadata,
                "holdout_resampled": False,
                "warning": (
                    "SMOTENC was never applied to validation or holdout data. Applying "
                    "oversampling before a split would leak synthetic neighbours into evaluation."
                ),
            },
            "final_holdout_metrics": holdout_metrics,
            "holdout_used_once_after_selection": True,
            "evaluation_limitations": provenance["evaluation_caveat"],
        },
        "feature_importance": {
            "artifact": "models/feature_importances.csv",
            "method": importance_method,
            "evaluation_split": "untouched stratified holdout",
        },
        "selection_rationale": (
            "The final model was selected solely from stratified validation results with "
            "recall weighted most heavily. The holdout result was calculated only after "
            "selection. A false negative can miss a fraudulent transaction, while a false "
            "positive can be routed for review."
        ),
    }

    # Persist only after every computation succeeds, keeping the consumer-facing
    # model, preprocessing pipeline, metadata, and importance table in sync.
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_joblib_dump(final_model, MODELS_DIR / "fraud_model.pkl")
    _atomic_joblib_dump(final_preprocessor, MODELS_DIR / "preprocessor.pkl")
    _atomic_json_dump(metadata, MODELS_DIR / "model_meta.json")
    _atomic_csv_dump(feature_importance, MODELS_DIR / "feature_importances.csv")

    print("\nSaved model artifacts:")
    print(f"  • {MODELS_DIR / 'fraud_model.pkl'}")
    print(f"  • {MODELS_DIR / 'preprocessor.pkl'}")
    print(f"  • {MODELS_DIR / 'model_meta.json'}")
    print(f"  • {MODELS_DIR / 'feature_importances.csv'}")
    print(
        "\nViva-safe summary: this result comes from a synthetic development fixture; "
        "it is not evidence of live UPI/NPCI fraud-detection performance."
    )

    return final_model, feature_importance, metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to a labelled PaySim-style CSV (default: data/transactions.csv).",
    )
    parser.add_argument(
        "--dataset-kind",
        choices=["auto", "synthetic", "public", "unknown"],
        default="auto",
        help="Declare provenance when replacing the built-in synthetic fixture.",
    )
    parser.add_argument(
        "--dataset-source",
        default=None,
        help="Human-readable source/URL description saved in model metadata.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=RANDOM_STATE,
        help=f"Random seed for all split/resampling/model steps (default: {RANDOM_STATE}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train(
        data_path=args.data,
        dataset_source=args.dataset_source,
        dataset_kind=args.dataset_kind,
        random_state=args.random_state,
    )


if __name__ == "__main__":
    main()
