"""
generate_data.py
----------------
Generates a realistic synthetic digital-payments dataset mirroring PaySim
schemas used in published fraud-detection research.

Eliminates deterministic target leakage by introducing:
  1. Stochastic accounting variations (fees, delayed settlements, unrecorded
     merchant terminal balances, overdrafts).
  2. Realistic distribution overlap between legitimate and fraudulent transactions.
  3. Mixed destination account types (both customer C... and merchant M...
     identities for legitimate and fraudulent transactions).

Columns produced:
  step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
  nameDest, oldbalanceDest, newbalanceDest, isFraud

Run once:  python generate_data.py
Output:    data/transactions.csv  (~100 000 rows, ~0.13% fraud)
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ── reproducibility ──────────────────────────────────────────────────────────
rng = np.random.default_rng(42)

N = 100_000          # total transactions
FRAUD_RATE = 0.0013  # ~0.13 % — realistic digital-payments imbalance
N_FRAUD = int(N * FRAUD_RATE)
N_LEGIT = N - N_FRAUD

TYPES = ["CASH_OUT", "PAYMENT", "TRANSFER", "CASH_IN", "DEBIT"]
# Fraud predominantly targets TRANSFER (fund exfiltration) and CASH_OUT (cashing out)
FRAUD_TYPES = ["TRANSFER", "CASH_OUT"]


def _gen_id(prefix: str, n: int) -> np.ndarray:
    """Generate random customer/merchant IDs like C123456789 or M987654321."""
    nums = rng.integers(100_000_000, 999_999_999, size=n)
    return np.array([f"{prefix}{x}" for x in nums])


def _make_legit(n: int) -> pd.DataFrame:
    """Generate n legitimate transactions with realistic banking variations."""
    t_type = rng.choice(TYPES, size=n, p=[0.35, 0.34, 0.16, 0.10, 0.05])
    amount = np.abs(rng.lognormal(mean=6.8, sigma=1.7, size=n)).clip(10, 2_000_000)

    # Origin balance dynamics
    old_orig = np.abs(rng.lognormal(mean=7.2, sigma=2.0, size=n))
    new_orig = np.zeros(n)
    scenario_orig = rng.choice(
        ["normal", "overdraft", "fee", "pending"],
        size=n,
        p=[0.75, 0.15, 0.07, 0.03],
    )
    for i, scenario in enumerate(scenario_orig):
        if scenario == "normal":
            new_orig[i] = max(old_orig[i] - amount[i], 0.0)
        elif scenario == "overdraft":
            old_orig[i] = rng.uniform(0.0, amount[i])
            new_orig[i] = 0.0
        elif scenario == "fee":
            fee = rng.uniform(5.0, 50.0)
            new_orig[i] = max(old_orig[i] - amount[i] - fee, 0.0)
        else:  # pending ledger update
            new_orig[i] = old_orig[i]

    # Destination balance dynamics
    old_dest = np.abs(rng.lognormal(mean=6.2, sigma=2.0, size=n))
    new_dest = np.zeros(n)
    scenario_dest = rng.choice(
        ["credit", "zero_unrecorded", "delayed", "fee"],
        size=n,
        p=[0.60, 0.25, 0.10, 0.05],
    )
    for i, scenario in enumerate(scenario_dest):
        if scenario == "zero_unrecorded":
            # In PaySim, external merchant terminals often have unrecorded 0.0 balances
            old_dest[i] = 0.0
            new_dest[i] = 0.0
        elif scenario == "delayed":
            new_dest[i] = old_dest[i]
        elif scenario == "fee":
            new_dest[i] = old_dest[i] + amount[i] * 0.985
        else:
            noise = rng.normal(0.0, 2.0)
            new_dest[i] = max(old_dest[i] + amount[i] + noise, 0.0)

    # Mixed destination types (not all merchants; P2P transfers go to customers)
    dest_prefix = np.where(rng.uniform(0, 1, size=n) < 0.65, "M", "C")
    name_dest = np.array([f"{p}{x}" for p, x in zip(dest_prefix, rng.integers(100_000_000, 999_999_999, size=n))])

    return pd.DataFrame({
        "step": rng.integers(1, 744, size=n),
        "type": t_type,
        "amount": amount.round(2),
        "nameOrig": _gen_id("C", n),
        "oldbalanceOrg": old_orig.round(2),
        "newbalanceOrig": new_orig.round(2),
        "nameDest": name_dest,
        "oldbalanceDest": old_dest.round(2),
        "newbalanceDest": new_dest.round(2),
        "isFraud": 0,
    })


def _make_fraud(n: int) -> pd.DataFrame:
    """Generate n fraudulent transactions with realistic adversary patterns."""
    t_type = rng.choice(FRAUD_TYPES, size=n, p=[0.55, 0.45])
    amount = np.abs(rng.lognormal(mean=9.2, sigma=1.3, size=n)).clip(5000, 5_000_000)

    # Origin balance dynamics
    old_orig = np.zeros(n)
    new_orig = np.zeros(n)
    scenario_orig = rng.choice(
        ["drain_small_resid", "partial_drain", "exact_drain"],
        size=n,
        p=[0.55, 0.30, 0.15],
    )
    for i, scenario in enumerate(scenario_orig):
        if scenario == "drain_small_resid":
            old_orig[i] = amount[i] + rng.uniform(20.0, 500.0)
            new_orig[i] = old_orig[i] - amount[i]
        elif scenario == "partial_drain":
            old_orig[i] = amount[i] * rng.uniform(1.3, 3.0)
            new_orig[i] = old_orig[i] - amount[i]
        else:
            old_orig[i] = amount[i]
            new_orig[i] = 0.0

    # Destination balance dynamics
    old_dest = np.abs(rng.lognormal(mean=5.5, sigma=1.8, size=n))
    new_dest = np.zeros(n)
    scenario_dest = rng.choice(
        ["credited_mule", "laundered_rapid", "zero_mule"],
        size=n,
        p=[0.50, 0.35, 0.15],
    )
    for i, scenario in enumerate(scenario_dest):
        if scenario == "credited_mule":
            new_dest[i] = old_dest[i] + amount[i]
        elif scenario == "laundered_rapid":
            new_dest[i] = old_dest[i]
        else:
            old_dest[i] = 0.0
            new_dest[i] = 0.0

    # Destination IDs: predominantly mule accounts (C), but includes rogue shell merchants (M)
    dest_prefix = np.where(rng.uniform(0, 1, size=n) < 0.60, "C", "M")
    name_dest = np.array([f"{p}{x}" for p, x in zip(dest_prefix, rng.integers(100_000_000, 999_999_999, size=n))])

    return pd.DataFrame({
        "step": rng.integers(1, 744, size=n),
        "type": t_type,
        "amount": amount.round(2),
        "nameOrig": _gen_id("C", n),
        "oldbalanceOrg": old_orig.round(2),
        "newbalanceOrig": new_orig.round(2),
        "nameDest": name_dest,
        "oldbalanceDest": old_dest.round(2),
        "newbalanceDest": new_dest.round(2),
        "isFraud": 1,
    })


def main():
    print(f"Generating {N_LEGIT:,} legitimate + {N_FRAUD:,} fraudulent transactions...")

    legit = _make_legit(N_LEGIT)
    fraud = _make_fraud(N_FRAUD)

    df = pd.concat([legit, fraud], ignore_index=True)
    # Shuffle so fraud isn't clustered
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    out = Path("data/transactions.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print(f"Saved {len(df):,} rows → {out}")
    print(f"\nClass distribution:\n{df['isFraud'].value_counts()}")
    print(f"\nFraud rate: {df['isFraud'].mean():.4%}")
    print(f"\nColumn dtypes:\n{df.dtypes}")


if __name__ == "__main__":
    main()

