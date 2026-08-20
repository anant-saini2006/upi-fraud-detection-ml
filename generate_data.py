"""
generate_data.py
----------------
Generates a realistic synthetic dataset that mirrors the PaySim digital-payments
schema used in the published literature on UPI-style fraud detection.

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
FRAUD_RATE = 0.0013  # ~0.13 % — realistic PaySim imbalance
N_FRAUD = int(N * FRAUD_RATE)
N_LEGIT = N - N_FRAUD

TYPES = ["CASH_OUT", "PAYMENT", "TRANSFER", "CASH_IN", "DEBIT"]
# Fraud only happens on CASH_OUT and TRANSFER (PaySim rule)
FRAUD_TYPES = ["CASH_OUT", "TRANSFER"]


def _gen_id(prefix: str, n: int) -> np.ndarray:
    """Generate random customer/merchant IDs like C123456789."""
    nums = rng.integers(100_000_000, 999_999_999, size=n)
    return np.array([f"{prefix}{x}" for x in nums])


def _make_legit(n: int) -> pd.DataFrame:
    """Generate n legitimate transactions."""
    t_type = rng.choice(TYPES, size=n, p=[0.35, 0.34, 0.16, 0.10, 0.05])
    amount = np.abs(rng.lognormal(mean=6.5, sigma=1.8, size=n)).clip(1, 2_000_000)

    old_orig = np.abs(rng.lognormal(mean=7, sigma=2, size=n))
    # Legitimate: balance decreases by amount (capped at 0)
    new_orig = np.maximum(old_orig - amount, 0)

    old_dest = np.abs(rng.lognormal(mean=6, sigma=2, size=n))
    # Legitimate: dest balance increases by amount
    new_dest = old_dest + amount

    return pd.DataFrame({
        "step": rng.integers(1, 744, size=n),           # up to 744 hours (31 days)
        "type": t_type,
        "amount": amount.round(2),
        "nameOrig": _gen_id("C", n),
        "oldbalanceOrg": old_orig.round(2),
        "newbalanceOrig": new_orig.round(2),
        "nameDest": _gen_id("M", n),
        "oldbalanceDest": old_dest.round(2),
        "newbalanceDest": new_dest.round(2),
        "isFraud": 0,
    })


def _make_fraud(n: int) -> pd.DataFrame:
    """
    Generate n fraudulent transactions.
    Fraud pattern: large CASH_OUT or TRANSFER where the origin account is
    drained to zero but the balance update is NOT reflected (mismatch).
    """
    t_type = rng.choice(FRAUD_TYPES, size=n, p=[0.5, 0.5])
    amount = np.abs(rng.lognormal(mean=8, sigma=1.5, size=n)).clip(1000, 10_000_000)

    old_orig = amount + np.abs(rng.normal(0, 100, size=n))   # account had (roughly) exactly that amount
    new_orig = np.zeros(n)                                    # drained to 0

    old_dest = np.abs(rng.lognormal(mean=5, sigma=1.5, size=n))
    # Fraud: dest balance NOT updated (money laundering pattern)
    new_dest = old_dest.copy()

    return pd.DataFrame({
        "step": rng.integers(1, 744, size=n),
        "type": t_type,
        "amount": amount.round(2),
        "nameOrig": _gen_id("C", n),
        "oldbalanceOrg": old_orig.round(2),
        "newbalanceOrig": new_orig.round(2),
        "nameDest": _gen_id("C", n),   # fraud goes to another customer, not merchant
        "oldbalanceDest": old_dest.round(2),
        "newbalanceDest": new_dest.round(2),
        "isFraud": 1,
    })


def main():
    print(f"Generating {N_LEGIT:,} legitimate + {N_FRAUD:,} fraudulent transactions...")

    legit = _make_legit(N_LEGIT)
    fraud = _make_fraud(N_FRAUD)

    df = pd.concat([legit, fraud], ignore_index=True)
    # Shuffle so fraud isn't all at the end
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
