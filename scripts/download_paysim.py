"""Download and validate the PaySim dataset from Kaggle.

Run from the repository root:
    .venv/bin/python scripts/download_paysim.py

Prerequisites:
    pip install kaggle
    Configure ~/.kaggle/kaggle.json with your API credentials.
    See: https://github.com/Kaggle/kaggle-api#api-credentials

The script downloads the PaySim1 dataset (~470 MB compressed) and validates
that its schema matches the preprocessing contract.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "paysim.csv"

# The exact Kaggle dataset slug.  Two popular copies exist; we prefer the
# primary upload by the dataset author (ealaxi/paysim1).
KAGGLE_DATASET = "ealaxi/paysim1"
EXPECTED_FILENAME = "PS_20174392719_1491204439457_log.csv"

# PaySim schema — must match the columns our preprocessor expects.
REQUIRED_COLUMNS = {
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
}


def download_with_kaggle_api() -> Path:
    """Download using the official Kaggle CLI/API."""
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        print(
            "The kaggle package is not installed.\n"
            "Install it with: pip install kaggle\n"
            "Then configure ~/.kaggle/kaggle.json.\n"
            "See: https://github.com/Kaggle/kaggle-api#api-credentials"
        )
        sys.exit(1)

    api = KaggleApi()
    api.authenticate()

    print(f"Downloading {KAGGLE_DATASET} from Kaggle...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Download to a temporary location and extract.
    download_dir = DATA_DIR / ".kaggle_download"
    download_dir.mkdir(parents=True, exist_ok=True)

    api.dataset_download_files(KAGGLE_DATASET, path=str(download_dir), unzip=False)

    # Find the zip file.
    zip_files = list(download_dir.glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError(
            f"No ZIP file found after downloading {KAGGLE_DATASET}."
        )

    zip_path = zip_files[0]
    print(f"Extracting {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find the CSV inside the zip.
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise FileNotFoundError("No CSV found inside the downloaded ZIP.")

        # Prefer the expected filename, fall back to the first CSV.
        target_name = (
            EXPECTED_FILENAME if EXPECTED_FILENAME in csv_names else csv_names[0]
        )

        print(f"Extracting {target_name} → {OUTPUT_PATH}")
        with zf.open(target_name) as source, OUTPUT_PATH.open("wb") as dest:
            # Stream in chunks to handle the ~470 MB file.
            while True:
                chunk = source.read(8 * 1024 * 1024)
                if not chunk:
                    break
                dest.write(chunk)

    # Clean up.
    zip_path.unlink()
    try:
        download_dir.rmdir()
    except OSError:
        pass

    return OUTPUT_PATH


def validate_schema(csv_path: Path) -> None:
    """Validate that the downloaded CSV has the expected PaySim schema."""
    import pandas as pd

    print(f"\nValidating schema of {csv_path}...")

    # Read just the header to check columns.
    header = pd.read_csv(csv_path, nrows=0)
    columns = set(header.columns)

    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(
            f"Schema mismatch: the downloaded CSV is missing columns: {sorted(missing)}.\n"
            f"Found columns: {sorted(columns)}\n"
            f"Expected: {sorted(REQUIRED_COLUMNS)}"
        )

    # Quick stats from a sample.
    sample = pd.read_csv(csv_path, nrows=10_000)
    total_preview = len(sample)
    fraud_preview = int(sample["isFraud"].sum()) if "isFraud" in sample.columns else 0

    # Count total rows (fast line count).
    with csv_path.open("rb") as f:
        total_rows = sum(1 for _ in f) - 1  # subtract header

    print(f"✓ Schema validated: {sorted(columns)}")
    print(f"✓ Total rows: {total_rows:,}")
    print(f"✓ Preview fraud rate (first {total_preview:,} rows): {fraud_preview}/{total_preview}")
    print(f"✓ File size: {csv_path.stat().st_size / (1024 * 1024):.1f} MB")

    # Check fraud types match PaySim expectations.
    if "type" in sample.columns:
        fraud_types = sample.loc[sample["isFraud"] == 1, "type"].unique().tolist()
        print(f"✓ Fraud transaction types in sample: {sorted(fraud_types)}")


def main() -> None:
    if OUTPUT_PATH.exists():
        response = input(
            f"{OUTPUT_PATH} already exists ({OUTPUT_PATH.stat().st_size / (1024 * 1024):.0f} MB).\n"
            "Re-download? [y/N]: "
        )
        if response.strip().lower() != "y":
            print("Skipping download. Validating existing file...")
            validate_schema(OUTPUT_PATH)
            return

    csv_path = download_with_kaggle_api()
    validate_schema(csv_path)

    print(
        f"\n✓ PaySim dataset ready at {csv_path}\n"
        "\nTo retrain on PaySim:\n"
        "  .venv/bin/python src/train_model.py \\\n"
        '    --data data/paysim.csv \\\n'
        '    --dataset-kind public \\\n'
        '    --dataset-source "Kaggle: PaySim synthetic financial dataset '
        '(https://www.kaggle.com/datasets/ealaxi/paysim1)"'
    )


if __name__ == "__main__":
    main()
