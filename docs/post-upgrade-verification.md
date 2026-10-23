# Post-Upgrade ML & Gateway Verification Report

**Project:** UPI Fraud Detection Using Machine Learning  
**Verification Date:** October 2026  
**Status:** Verification Completed — All Checks Verified  
**Artifact Path:** `docs/post-upgrade-verification.md`  
**Reference Document:** `docs/ml-validation-audit.md`  

---

## 1. Executive Summary

Following the comprehensive machine learning pipeline overhaul and dashboard upgrade, an independent post-upgrade verification was executed. The objectives were to:
1. Confirm that the deterministic target leakage identified in `docs/ml-validation-audit.md` has been successfully eliminated from `data/transactions.csv`.
2. Inspect the retrained model artifacts, feature importances, and mathematical alignment between displayed metrics and the held-out confusion matrix.
3. Verify feature contracts between training and real-time inference (notably `step` vs. `hour_of_day`).
4. Execute non-destructive unit and contract test suites.
5. Trace event and persistence flows across the Admin Console, transaction simulator, and payment gateway subsystems to identify architectural alignments and discrepancies.

### Summary of Verification Verdicts:
* **Target Leakage Remediation:** **CONFIRMED ELIMINATED.** The naive heuristic rule `errorBalanceDest > 1.0` (which previously produced 100% precision and recall with 0 false positives) now yields a precision of **0.11%**, recall of **49.23%**, and false positive rate of **58.06%**. Single-feature shortcut rules fail completely.
* **Feature Importances:** **REALISTIC & MULTIVARIATE.** Permutation feature importance on the untouched holdout demonstrates that predictions are driven primarily by transaction `amount` (0.71 PR-AUC drop), complemented by behavioural balance mismatch signals and transaction type.
* **Metric Alignment:** **MATHEMATICALLY EXACT.** The displayed holdout test metrics (Accuracy 99.87%, Precision 50.00%, Recall 88.46%, F1 63.89%, FPR 0.12%) reconcile precisely with the 20,000-sample held-out confusion matrix (TN=19,951, FP=23, FN=3, TP=23). Outer holdout test metrics are cleanly separated from inner model-selection validation metrics.
* **Feature Contract (`step` vs `hour_of_day`):** **FIXED.** The API handles omitted `step` values by pinning to a mid-timeline cycle (`15 * 24 + hour_of_day`), ensuring both $z \approx 0$ under standardization and identical hourly modulo extraction (`step % 24 == hour_of_day`).
* **Test Suite:** **12 of 12 PASSED (100%).** All API contract and gateway decision policy unit tests passed without failure or regression.
* **Subsystem Architecture:** **THREE SEPARATE FLOWS IDENTIFIED.** While the simulated payment gateway (`/v1`) and Admin Console (`/admin`) share an event and persistence ledger (`payments`, `reviews`, `accounts`), the newly added Razorpay Standard Checkout (`/payments/*`) persists independently in `gateway_payment_orders` / `gateway_webhook_events` (SQLAlchemy / SQLite) and its fraud adapter deliberately flags `needs_feature_adapter` to prevent balance feature fabrication.

---

## 2. Git Status & Existing Changes Review

Inspection of the working tree confirmed 17 modified files and 6 untracked files. No files were reverted, modified, or overwritten during this verification phase.

### Unstaged Working Tree Changes:
| Category | File | Description |
|---|---|---|
| **Configuration** | `.gitignore` | Ignores local databases (`payments_local.db`) and payment environment files. |
| **Backend & API** | `api/index.py` | Added fallback for `step`, integrated Razorpay router mount, aligned metric schemas. |
| **Backend & API** | `api/requirements.txt` | Standard project dependencies. |
| **Data & Generator** | `data/transactions.csv` | Regenerated 100,000-record dataset with realistic banking balance dynamics. |
| **Data & Generator** | `generate_data.py` | Updated generator introducing noise, unrecorded terminal balances, and varied drain dynamics. |
| **Model Artifacts** | `models/fraud_model.pkl` | Retrained Histogram Gradient Boosting classifier. |
| **Model Artifacts** | `models/preprocessor.pkl` | Serialized `ColumnTransformer` fitted solely on development data. |
| **Model Artifacts** | `models/model_meta.json` | Updated metadata schema with honest provenance and holdout validation breakdown. |
| **Model Artifacts** | `models/feature_importances.csv` | Permutation importances measured on the untouched holdout partition. |
| **Preprocessing & Train**| `src/preprocessing.py` | Robust validation and handling of raw and engineered columns. |
| **Preprocessing & Train**| `src/train_model.py` | Two-tier stratified partitioning, SMOTE-NC isolated strictly to training partitions. |
| **Frontend UI** | `frontend/src/app/page.tsx` | Dashboard home reflecting retrained model parameters and honest disclaimers. |
| **Frontend UI** | `frontend/src/app/performance/page.tsx` | Comprehensive performance page with confusion matrix, PR-AUC, and baseline comparison. |
| **Frontend UI** | `frontend/src/app/shop/page.tsx` | Merchant checkout view supporting both simulated UPI and Razorpay payment flows. |
| **Frontend UI** | `frontend/src/components/AppShell.tsx`| Navigation bar updates. |
| **Frontend UI** | `frontend/src/lib/api.ts` | Frontend client typed interfaces for gateway, admin, and metrics. |
| **Tests** | `tests/test_api_contract.py` | API contract tests dynamically querying dataset rows. |

### Untracked Files:
* `api/.env.payments.example` — Template environment variables for Razorpay credentials.
* `api/payment_integration/` — Implementation of Razorpay orders, signatures, webhook handler, and fraud adapter.
* `api/requirements-payments.txt` — Razorpay SDK and SQLAlchemy dependencies.
* `docs/` — Forensic documentation including `ml-validation-audit.md` and this report.
* `frontend/src/components/MockRazorpayModal.tsx` — Client-side checkout modal for zero-KYC demo testing.
* `frontend/src/components/RazorpayPayButton.tsx` — Checkout button triggering the Razorpay modal flow.

---

## 3. Balance Heuristic Re-run & Comparison with Audit

### 3.1. Dataset Summary Statistics
* **Total Transactions ($N$):** 100,000
* **Legitimate Transactions (Class 0):** 99,870 (99.87%)
* **Fraud Transactions (Class 1):** 130 (0.13%)
* **Duplicate Rows:** 0 (Confirmed unique across all columns)

### 3.2. Destination Balance Heuristic Test
Rule: 
$$\text{errorBalanceDest} = \text{oldbalanceDest} + \text{amount} - \text{newbalanceDest} > 1.0$$

#### Empirical Comparison:
| Metric | Pre-Upgrade Audit (`docs/ml-validation-audit.md`) | Post-Upgrade Current (`data/transactions.csv`) | Impact / Verdict |
|---|---|---|---|
| **True Negatives (TN)** | 99,870 | **41,884** | Legitimate transactions now exhibit balance differences. |
| **False Positives (FP)** | 0 | **57,986** | 58.06% of legitimate transactions trigger this rule. |
| **False Negatives (FN)** | 0 | **66** | 50.77% of frauds are missed by this rule. |
| **True Positives (TP)** | 130 | **64** | Only 49.23% of frauds trigger this rule. |
| **Accuracy** | 100.00% | **41.95%** | Fails completely as a classifier. |
| **Precision** | **100.00%** | **0.1102%** | **Leakage eliminated.** (Down from 100% to baseline noise level). |
| **Recall** | **100.00%** | **49.2308%** | **Deterministic shortcut broken.** |
| **False Positive Rate (FPR)** | **0.00%** | **58.0615%** | Massively noisy on legitimate banking operations. |

### 3.3. Origin Balance Heuristic Test
Rule:
$$\text{errorBalanceOrig} = \text{newbalanceOrig} + \text{amount} - \text{oldbalanceOrg} < -0.05$$

#### Empirical Comparison:
| Metric | Pre-Upgrade Audit (`docs/ml-validation-audit.md`) | Post-Upgrade Current (`data/transactions.csv`) | Impact / Verdict |
|---|---|---|---|
| **True Negatives (TN)** | 99,870 | **95,951** | Most legitimate transactions stay above threshold. |
| **False Positives (FP)** | 0 | **3,919** | Legitimate transactions with fees or adjustments produce noise. |
| **False Negatives (FN)** | 0 | **130** | **100% of frauds are missed.** |
| **True Positives (TP)** | 130 | **0** | **0% caught.** |
| **Precision** | **100.00%** | **0.0000%** | **Rule completely invalid.** |
| **Recall** | **100.00%** | **0.0000%** | **Rule completely invalid.** |

### 3.4. Feature Distribution Analysis by Ground Truth Class
* **`errorBalanceDest`**:
  * *Legitimate:* Min = $-8.83$, Max = $+2,000,000.00$, Mean = $+1,440.23$, Std = $13,039.10$
  * *Fraud:* Min = $-0.01$, Max = $+87,125.40$, Mean = $+9,589.02$, Std = $17,109.24$
  * *Observation:* In legitimate transactions, external merchant transactions frequently record 0.0 balances or transaction fees, creating natural variations overlapping with fraudulent transfers.
* **`errorBalanceOrig`**:
  * *Legitimate:* Min = $-50.00$, Max = $+1,998,581.33$, Mean = $+2,742.25$, Std = $18,146.47$
  * *Fraud:* Min = $-0.01$, Max = $+0.01$, Mean = $-0.0003$, Std = $0.0037$
  * *Observation:* Fraudulent origin balances are no longer synthesized with deterministic negative offsets; transactions balance mathematically according to realistic ledger entries.

---

## 4. Feature Importance & Multivariable Decision Boundary

### 4.1. Permutation Importance Results
Permutation importance was evaluated on the untouched outer holdout dataset ($N = 20,000$) measuring the mean decrease in Precision-Recall AUC (PR-AUC) when each feature is permuted:

| Rank | Feature | Importance (PR-AUC Drop) | Interpretation |
|---|---|---|---|
| 1 | `amount` | **0.7106** | Primary discriminator; fraud amounts are substantially elevated. |
| 2 | `errorBalanceOrig` | **0.3792** | Secondary indicator of abnormal account draining. |
| 3 | `errorBalanceDest` | **0.3466** | Secondary indicator of uncredited/mule recipient accounts. |
| 4 | `type_PAYMENT` | **0.1637** | Categorical risk factor; payments have lower base fraud prevalence. |
| 5 | `newbalanceOrig` | **0.1434** | Post-transaction liquidity status. |
| 6 | `oldbalanceOrg` | **0.0952** | Prior balance level. |
| 7 | `oldbalanceDest` | **0.0601** | Prior recipient liquidity. |
| 8 | `type_CASH_IN` | **0.0301** | Categorical factor. |
| 9 | `type_DEBIT` | **0.0299** | Categorical factor. |
| 10 | `newbalanceDest` | **0.0279** | Post-transaction recipient status. |
| 11 | `step` | **0.0065** | Simulation timeline progress. |
| 12 | `hour_of_day` | **0.0026** | Circadian diurnal transaction pattern. |
| 13 | `is_high_value` | **0.0000** | Absorbed by continuous `amount` signal. |
| 14 | `type_CASH_OUT` | **-0.0035** | Minor permutation variance. |
| 15 | `type_TRANSFER` | **-0.0248** | Minor permutation variance. |

### 4.2. Analytical Finding
In the previous implementation, the model achieved 100% metrics because `errorBalanceDest` alone determined the label. Currently:
1. `amount` is the leading predictor, which aligns with domain realities in financial crime: large-scale transfers carry higher exfiltration risk.
2. Balance error features (`errorBalanceOrig` and `errorBalanceDest`) act as **contextual interaction terms** rather than isolated deterministic shortcuts.
3. The decision surface requires genuine multi-tree splits combining transaction amount, sender liquidity depletion, and destination crediting anomalies.

---

## 5. Verification of Model Metrics & Confusion Matrix

### 5.1. Mathematical Consistency of Displayed Metrics
The saved winner is **Histogram Gradient Boosting**. The metrics displayed on the dashboard (`/performance`) and returned by `/api/performance` were cross-checked against the 20,000-sample held-out confusion matrix:

$$\text{Held-Out Confusion Matrix: } \begin{pmatrix} \text{TN} = 19,951 & \text{FP} = 23 \\ \text{FN} = 3 & \text{TP} = 23 \end{pmatrix}$$

$$\text{Total Samples } = 19,951 + 23 + 3 + 23 = 20,000 \quad (\text{Legitimate} = 19,974, \text{ Fraud} = 26)$$

* **Accuracy:**
  $$\frac{\text{TP} + \text{TN}}{N} = \frac{23 + 19,951}{20,000} = \frac{19,974}{20,000} = 0.998700 \implies \mathbf{99.87\%}$$
* **Precision:**
  $$\frac{\text{TP}}{\text{TP} + \text{FP}} = \frac{23}{23 + 23} = \frac{23}{46} = 0.500000 \implies \mathbf{50.00\%}$$
* **Recall (Sensitivity):**
  $$\frac{\text{TP}}{\text{TP} + \text{FN}} = \frac{23}{23 + 3} = \frac{23}{26} = 0.884615 \implies \mathbf{88.46\%}$$
* **F1 Score:**
  $$2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} = 2 \times \frac{0.5000 \times 0.884615}{0.5000 + 0.884615} = \frac{0.884615}{1.384615} = 0.638889 \implies \mathbf{63.89\%}$$
* **False Positive Rate (FPR):**
  $$\frac{\text{FP}}{\text{FP} + \text{TN}} = \frac{23}{23 + 19,951} = \frac{23}{19,974} = 0.001151 \implies \mathbf{0.12\%}$$
* **ROC-AUC:** $\mathbf{0.9995}$
* **PR-AUC (Average Precision):** $\mathbf{0.8446}$

**Verdict:** The displayed metrics agree with mathematical precision. Every figure displayed on the dashboard cards matches the confusion-matrix calculation exactly.

### 5.2. Distinction Between Outer Holdout and Model-Selection Validation
A common source of confusion in ML audits is conflating validation metrics (used to select model architectures) with holdout test metrics (used to evaluate the selected model). The codebase strictly separates these splits:

| Dimension | Model-Selection Validation Split | Outer Holdout Test Split |
|---|---|---|
| **Purpose** | Architecture comparison & hyperparameter tuning | Final generalization estimate |
| **Partition Size** | 20,000 rows (25% of 80,000 Development partition) | 20,000 rows (20% of 100,000 Total dataset) |
| **Class Distribution**| 19,974 Legit / 26 Fraud | 19,974 Legit / 26 Fraud |
| **Training Partition**| 60,000 rows (SMOTE-NC applied to 60k train only) | 80,000 rows (SMOTE-NC applied to 80k dev only) |
| **Evaluation Frequency**| Evaluated across 4 models during `src/train_model.py` | Evaluated **once** on the final selected model |
| **Model Comparison** | * Dummy: Recall 0.0%, Precision 0.0%, F1 0.0%<br>* Logistic Regression: Recall 100.0%, Precision 5.83%, F1 11.02%<br>* Random Forest: Recall 92.31%, Precision 27.27%, F1 42.11%<br>* Hist Gradient Boosting: Recall 96.15%, Precision 48.08%, F1 64.10% | * Hist Gradient Boosting (Winner):<br>Recall **88.46%**<br>Precision **50.00%**<br>F1 **63.89%**<br>PR-AUC **84.46%** |

---

## 6. Training-to-Inference Feature Contract (`step` vs. `hour_of_day`)

### 6.1. Previous Vulnerability (Bug 4 in Audit)
Previously, `api/index.py` passed `transaction.hour_of_day` (0 to 23) directly into the raw `step` input. Because the training data `step` had $\mu = 371.5$ and $\sigma = 214.7$, passing an hour (e.g., 14) caused:
$$z_{\text{step}} = \frac{14 - 371.5}{214.7} \approx -1.66$$
The model received an input pinned to approximately $-1.7$ standard deviations at all times.

### 6.2. Verified Resolution in `api/index.py`
In `api/index.py` (lines 396–400):
```python
step_value = (
    transaction.step
    if transaction.step is not None
    else (15 * 24 + transaction.hour_of_day)
)
```
1. **Modulo Integrity:**
   $$\text{step\_value} \pmod{24} = (15 \times 24 + \text{hour\_of\_day}) \pmod{24} = \text{hour\_of\_day}$$
   When `PaySimFeatureEngineer` computes `engineered["hour_of_day"] = frame["step"] % 24`, it derives the exact `hour_of_day` entered by the client.
2. **StandardScaler Centering:**
   $15 \times 24 + 12 = 372$, which sits directly at the empirical mean of the 31-day simulation ($\mu \approx 371.5$). The standardized $z$-score is centered near $0.0$, avoiding out-of-distribution distortion when `step` is omitted.
3. **Optional Precision:**
   If a client provides an explicit simulation step ($1 \le \text{step} \le 744$), `TransactionInput` accepts and utilizes it directly.

---

## 7. Test Suite Execution Results

The non-destructive unit and contract test suites were executed using the project's local virtual environment (`./.venv/bin/python -m unittest discover tests`).

```
Ran 12 tests in 0.087s
OK
```

### Breakdown of Passing Tests:
1. `test_health_reports_loaded_artifacts` (`test_api_contract.py`): Verifies model, preprocessor, and dataset are loaded and healthy.
2. `test_prediction_accepts_raw_schema_and_returns_probability` (`test_api_contract.py`): Validates inference pipeline against dataset rows.
3. `test_transaction_type_is_normalised_and_checked` (`test_api_contract.py`): Verifies uppercase normalization and rejection of invalid transaction types.
4. `test_dashboard_and_evaluation_routes_return_real_data` (`test_api_contract.py`): Verifies `/api/stats`, charts, and `/api/performance` return valid non-empty dictionaries.
5. `test_csv_analysis_keeps_uploaded_data_separate_from_model_training` (`test_api_contract.py`): Guarantees user-uploaded CSVs do not mutate model training data.
6. `test_decision_policy_thresholds` (`test_decision_policy.py`): Validates routing logic (`succeeded` < 0.30, `requires_review` 0.30–0.70, `blocked` $\ge$ 0.70).
7. `test_reasons_generation_reasons_length_and_content` (`test_decision_policy.py`): Validates human-readable explanatory reasons for risk verdicts.
8. `test_scoring_response_contract_validation` (`test_decision_policy.py`): Verifies Pydantic schema validation for scoring contracts.
9. `test_threshold_settings_constraint` (`test_decision_policy.py`): Ensures review threshold is strictly less than block threshold.
10. `test_balance_update_logic_for_succeeded` (`test_decision_policy.py`): Confirms sender and receiver balances update correctly on settled payments.
11. `test_balance_update_logic_for_blocked` (`test_decision_policy.py`): Confirms blocked payments do NOT deduct sender or credit receiver balances.
12. `test_balance_update_logic_for_requires_review` (`test_decision_policy.py`): Confirms under-review payments hold balances without mutating the ledger.

---

## 8. Subsystem Architecture & Persistence Flow Analysis

An end-to-end inspection of event and persistence flows across the codebase revealed that the application is composed of **three distinct subsystems**:

```
+----------------------------------------------------------------------------------------------------+
|                                    1. DIRECT ML PREDICTOR                                          |
|  [Frontend /predict] ---> POST /api/predict ---> [api/index.py]                                    |
|                                                      |                                             |
|                                                      v                                             |
|                                            Table: predictions (PostgreSQL/Neon)                    |
+----------------------------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------------------------+
|                                 2. SIMULATED VPA GATEWAY                                           |
|  [Frontend /shop & /checkout] ---> POST /v1/payment_intents ---> [api/gateway.py]                 |
|                                                      |                                             |
|                                                      v                                             |
|                             Tables: payments, accounts, reviews, settings                          |
|                                                      ^                                             |
|                                                      |                                             |
|  [Frontend /admin] <------------ GET /api/admin/payments <--- [api/admin.py]                       |
+----------------------------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------------------------+
|                                 3. RAZORPAY CHECKOUT GATEWAY                                       |
|  [Frontend RazorpayPayButton] ---> POST /payments/orders ---> [api/payment_integration/...]        |
|  [Mock/Real Razorpay Popup]   ---> POST /payments/verify               |                           |
|                                                      v                 v                           |
|                                         score_payment (Adapter)        Tables:                     |
|                                         (returns needs_feature_adapter) gateway_payment_orders     |
|                                                                        gateway_webhook_events      |
|                                                                        (SQLite/PostgreSQL)         |
+----------------------------------------------------------------------------------------------------+
```

### 8.1. Subsystem Breakdown
1. **Direct ML Predictor (`/api/predict` & `/predict`)**:
   * Takes PaySim raw features (`amount`, `transaction_type`, `old_balance_orig`, etc.).
   * Directly invokes `_PREPROCESSOR.transform()` and `_MODEL.predict_proba()`.
   * Records inference transactions in the `predictions` table via `record_prediction()`.
   * Visible in `/api/predictions` history; completely decoupled from payment intent ledger.
2. **Simulated Payment Gateway & Admin Console (`/v1` & `/api/admin` & `/admin`)**:
   * Models Stripe/UPI payment intents between simulated `@testpay` virtual payment addresses.
   * Manages ledger balances in the `accounts` table.
   * Scores transactions using threshold settings (`review_threshold=0.30`, `block_threshold=0.70`).
   * Transitions payments into `succeeded`, `requires_review`, or `blocked`.
   * The Admin Console (`/admin`) connects directly to this flow, displaying live incoming payments and enabling manual reviews.
3. **Razorpay Standard Checkout / Merchant Store (`/payments/*` & `/shop`)**:
   * Production-style payment gateway integration using Razorpay orders, HMAC-SHA256 signature verification, and webhook replay protection.
   * Persists orders in `gateway_payment_orders` and webhooks in `gateway_webhook_events` using SQLAlchemy.
   * Defaults to local SQLite (`payments_local.db`) if Neon PostgreSQL is unavailable.

### 8.2. Identified Architectural Mismatch
* **Disconnection from Admin Console:**
  Orders placed through the Razorpay Standard Checkout flow (`/payments/orders` / `MockRazorpayModal`) are recorded exclusively in `gateway_payment_orders`. They **do not** create rows in the `payments` table queried by `api/admin.py`. As a result, payments made via Razorpay do not show up in the Admin Console live feed (`/admin`).
* **Feature Set Incompatibility in Fraud Adapter:**
  In `api/payment_integration/payment_fraud_adapter.py`, the scoring function returns `needs_feature_adapter` (`probability: None`). This is an intentional and defensible design choice: real payment gateway webhooks transmit merchant order data (amount, currency, payment method, customer contact), but do **not** supply PaySim-style sender/receiver bank balance fields (`oldbalanceOrg`, `newbalanceOrig`, etc.). Rather than fabricating fake balances, the adapter gracefully defers scoring.

---

## 9. Recommendations for Next Steps

1. **Unify Admin Live Feed with Gateway Orders (Optional Future Enhancement):**
   * If the user desires Razorpay orders to appear in the Admin Console, create a bridge query or view in `api/admin.py` that unions `payments` with `gateway_payment_orders`, mapping gateway fields into the `PaymentIntentResponse` schema.
2. **Payment Gateway Feature Adapter:**
   * To enable real ML scoring on Razorpay payments without synthetic balance inputs, train a secondary lightweight classifier solely on transaction attributes available at checkout (e.g., amount, hour, payment method, recipient category).
3. **External Dataset Validation:**
   * Before presenting results beyond capstone demonstration, validate the Histogram Gradient Boosting model against an external, publicly documented digital-payments dataset.

---
*Report compiled autonomously following strict non-destructive verification protocols.*
