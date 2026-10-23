"""Safe placeholder for connecting the saved ML pipeline to gateway payments.

The project's fraud model was trained on PaySim-like synthetic data whose
feature set includes sender/receiver account balances and transaction-step
counters.  A Razorpay payment webhook does **not** provide those fields.

**Do not fill missing features with zeroes or guessed values.**

This adapter intentionally returns ``needs_feature_adapter`` until the
developer either:

1. Maps real, available gateway fields to the saved preprocessing pipeline, or
2. Trains a separate model using features legitimately available from the
   payment gateway (amount, method, currency, timestamp, etc.).

See the project README and the ``api/index.py`` prediction route for the
current feature pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("payment_integration.fraud_adapter")


def score_payment(payment: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a captured Razorpay payment for fraud risk.

    Parameters
    ----------
    payment : dict
        The ``payment.entity`` object from Razorpay (either fetched via
        ``client.payment.fetch()`` or extracted from a webhook payload).

    Returns
    -------
    dict
        ``{"status": "...", "probability": float | None, "detail": str}``

    Current behaviour
    -----------------
    Always returns ``needs_feature_adapter``.  Replace the body of this
    function once you have mapped the available features.
    """

    # -----------------------------------------------------------------------
    # Example of what the final implementation might look like:
    #
    #   from api.index import _MODEL, _PREPROCESSOR
    #
    #   amount  = payment.get("amount", 0) / 100          # paise → INR
    #   method  = payment.get("method", "unknown")        # upi / card / …
    #   # … map other available fields …
    #
    #   # Build a DataFrame matching the preprocessor's expected columns
    #   import pandas as pd
    #   row = pd.DataFrame([{
    #       "amount": amount,
    #       "type": method.upper(),
    #       "step": ???,                 # ← NOT available from the gateway
    #       "oldbalanceOrg": ???,        # ← NOT available from the gateway
    #       "newbalanceOrig": ???,       # ← NOT available
    #       "oldbalanceDest": ???,       # ← NOT available
    #       "newbalanceDest": ???,       # ← NOT available
    #   }])
    #
    #   X = _PREPROCESSOR.transform(row)
    #   prob = float(_MODEL.predict_proba(X)[0, 1])
    #   label = "fraud" if prob >= 0.5 else "legitimate"
    #   return {"status": label, "probability": prob, "detail": "model_v1"}
    # -----------------------------------------------------------------------

    logger.info(
        "score_payment called for payment %s (amount=%s, method=%s).  "
        "Returning needs_feature_adapter — adapter not yet implemented.",
        payment.get("id"),
        payment.get("amount"),
        payment.get("method"),
    )

    return {
        "status": "needs_feature_adapter",
        "probability": None,
        "detail": (
            "The saved model requires balance-related features that are not "
            "available from the payment gateway.  See payment_fraud_adapter.py."
        ),
    }
