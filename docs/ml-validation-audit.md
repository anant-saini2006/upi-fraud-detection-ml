# Comprehensive Machine Learning Pipeline & Validation Audit Report

**Project:** UPI Fraud Detection Using Machine Learning  
**Audit Date:** October 2026  
**Status:** Audit Completed — Awaiting User Review Before Application Changes  
**Artifact Version:** 1.0  
**Target Codebase:** `generate_data.py`, `src/preprocessing.py`, `src/train_model.py`, `api/index.py`, `models/model_meta.json`

---

## 1. Executive Summary

A comprehensive forensic audit of the machine learning training, feature engineering, resampling, and evaluation pipeline was conducted. The audit was triggered by dashboard and metadata reports of **100% Precision, 100% Recall, 100% F1-score, and 1.0000 ROC-AUC** across multiple classification models (Logistic Regression, Random Forest, Histogram Gradient Boosting) on a synthetic dataset of 100,000 transactions containing only 130 fraud-labelled records (0.13% positive class prevalence).

### Key Audit Findings:
1. **The 100% metrics are NOT a result of algorithmic superiority; they are caused by severe deterministic target leakage in the synthetic dataset generator (`generate_data.py`).**
2. In `generate_data.py`, balance update logic was constructed using exact algebraic equations for legitimate transactions, but was frozen or drained deterministically for fraud transactions.
3. As a result, the engineered features `errorBalanceDest` and `errorBalanceOrig` in `src/preprocessing.py` become **exact mathematical proxies for the ground truth label `isFraud`**. A trivial single-feature threshold rule (`errorBalanceDest > 1.0`) achieves 100% precision and 100% recall with zero false positives and zero false negatives across all 100,000 samples without requiring any machine learning model.
4. **Resampling isolation is correctly implemented in `src/train_model.py`.** SMOTENC is strictly applied to training splits and never leaks into validation or holdout splits. However, because the synthetic generator baked deterministic separability into the underlying records, the held-out test split exhibits the identical leakage as the training set.
5. **A confirmed inference contract bug exists in `api/index.py` (line 397).** The API passes `hour_of_day` (0–23) into the `step` column, which was trained on cumulative timeline hour steps (1–744, mean 371.5, scale 214.7). This forces inference-time `step` values to $z \approx -1.73$ and corrupts the derived feature calculations.
6. **No baseline classifier (`DummyClassifier`) is tracked or reported.** On this 99.87% imbalanced dataset, a naive majority-class classifier achieves 99.87% accuracy, illustrating that accuracy is entirely uninformative in this domain.

---

## 2. Pipeline Architecture & Component Inspection

The table below summarizes the inspection across all ML pipeline stages:

| Component | File Path | Mechanism | Audit Verdict |
|---|---|---|---|
| **Dataset Generator** | `generate_data.py` | Generates 100,000 synthetic rows (99,870 legit, 130 fraud) mimicking PaySim schema. | **Fatal Target Leakage:** Deterministic formulas separate classes with 100% purity. |
| **Feature Engineering** | `src/preprocessing.py` | `PaySimFeatureEngineer` computes `hour_of_day`, `is_high_value`, `errorBalanceOrig`, `errorBalanceDest`. | **Proxy Amplification:** Calculates balance errors that directly expose the synthetic generation leakage. |
| **Preprocessing & Scaling** | `src/preprocessing.py` | `ColumnTransformer`, `StandardScaler`, `signed_log1p`, `OneHotEncoder`. | **Clean:** Leakage-safe, quantile fitted only on training data, serializable pipeline. |
| **Resampling (SMOTE)** | `src/train_model.py` | `SMOTENC` applied to training partitions with numeric scaler for neighbor search. | **Clean:** Applied strictly to `X_selection_train` and `X_development`. Holdout and validation are untouched. |
| **Train/Test Splitting** | `src/train_model.py` | Nested stratified splits: 80% Dev / 20% Holdout; Dev further split 75% Train / 25% Validation. | **Clean:** Stratified splitting preserved across all splits. |
| **Model Selection** | `src/train_model.py` | Evaluates models on validation split using weighted score: $0.60 \times \text{Recall} + 0.25 \times \text{F1} + 0.15 \times \text{PR-AUC}$. | **Clean:** Selection relies solely on validation metrics. Simpler model chosen on tie (Logistic Regression). |
| **Saved Artifacts** | `models/` | `fraud_model.pkl`, `preprocessor.pkl`, `model_meta.json`, `feature_importances.csv`. | **Documented:** Persists metadata with transparent caveats; reports 1.0000 across all metrics. |
| **Metrics API** | `api/index.py` | `/api/performance` regenerates 20% outer test split and computes metrics; `/api/predict` runs inference. | **Bug in Inference:** Mismatch between `step` feature definition in training vs inference API. |

---

## 3. Confirmed Bugs & Critical Vulnerabilities

### Bug 1: Deterministic Target Leakage in Destination Balance (`errorBalanceDest`)
* **Location:** `generate_data.py` (lines 48–49 vs line 79) and `src/preprocessing.py` (lines 415–417).
* **Mechanism:**
  - In `_make_legit(n)`:
    ```python
    old_dest = np.abs(rng.lognormal(mean=6, sigma=2, size=n))
    new_dest = old_dest + amount
    ```
  - In `_make_fraud(n)`:
    ```python
    old_dest = np.abs(rng.lognormal(mean=5, sigma=1.5, size=n))
    new_dest = old_dest.copy()
    ```
  - In `src/preprocessing.py`, the engineered feature is computed as:
    $$\text{errorBalanceDest} = \text{oldbalanceDest} + \text{amount} - \text{newbalanceDest}$$
* **Mathematical Consequence:**
  - **For Legitimate Records:**
    $$\text{errorBalanceDest} = \text{old\_dest} + \text{amount} - (\text{old\_dest} + \text{amount}) = 0.00$$
    Due to 2-decimal rounding in CSV storage, $\text{errorBalanceDest} \in [-0.01, +0.01]$.
  - **For Fraud Records:**
    $$\text{errorBalanceDest} = \text{old\_dest} + \text{amount} - \text{old\_dest} = \text{amount}$$
    Since fraud transaction amounts are clipped to $[1,000, 10,000,000]$, $\text{errorBalanceDest} \ge 1,000.00$.
* **Empirical Verification:**
  - Range for Legitimate ($N = 99,870$): Min: $-0.0100$, Max: $+0.0100$, Mean: $+0.000011$.
  - Range for Fraud ($N = 130$): Min: $+1,000.00$, Max: $+143,663.14$, Mean: $+9,787.81$.
  - **Proof:** A naive decision rule `errorBalanceDest > 1.0` achieves **100% Accuracy, 100% Precision, 100% Recall, and 1.0000 ROC-AUC** across all 100,000 records.

### Bug 2: Deterministic Target Leakage in Origin Balance (`errorBalanceOrig`)
* **Location:** `generate_data.py` (lines 44–45 vs lines 74–75) and `src/preprocessing.py` (lines 412–414).
* **Mechanism:**
  - In `_make_legit(n)`:
    ```python
    new_orig = np.maximum(old_orig - amount, 0)
    ```
  - In `_make_fraud(n)`:
    ```python
    old_orig = amount + np.abs(rng.normal(0, 100, size=n))
    new_orig = np.zeros(n)
    ```
  - In `src/preprocessing.py`:
    $$\text{errorBalanceOrig} = \text{newbalanceOrig} + \text{amount} - \text{oldbalanceOrg}$$
* **Mathematical Consequence:**
  - **For Legitimate Records:**
    - If $\text{old\_orig} \ge \text{amount}$: $\text{new\_orig} = \text{old\_orig} - \text{amount} \implies \text{errorBalanceOrig} = 0.00$.
    - If $\text{old\_orig} < \text{amount}$: $\text{new\_orig} = 0 \implies \text{errorBalanceOrig} = \text{amount} - \text{old\_orig} \ge 0.00$.
    - Therefore, for all legitimate transactions: $\text{errorBalanceOrig} \ge -0.01$.
  - **For Fraud Records:**
    $$\text{errorBalanceOrig} = 0 + \text{amount} - (\text{amount} + |\mathcal{N}(0, 100)|) = -|\mathcal{N}(0, 100)| \le 0.00$$
    With $|\mathcal{N}(0, 100)|$, the difference is strictly negative.
* **Empirical Verification:**
  - Range for Legitimate ($N = 99,870$): Min: $-0.0100$, Max: $+1,998,838.49$, Mean: $+2,588.27$.
  - Range for Fraud ($N = 130$): Min: $-295.50$, Max: $-0.36$, Mean: $-78.39$.
  - **Proof:** A single threshold `errorBalanceOrig < -0.05` classifies all 100,000 transactions with **100% precision and 100% recall** independently.

### Bug 3: Absolute Label Separation in Destination Identifier Prefix (`nameDest`)
* **Location:** `generate_data.py` (line 58 vs line 88).
* **Mechanism:**
  - In `_make_legit`: `"nameDest": _gen_id("M", n)` (100% of destination IDs start with `"M"` for Merchant).
  - In `_make_fraud`: `"nameDest": _gen_id("C", n)` (100% of destination IDs start with `"C"` for Customer).
* **Empirical Verification:**
  - Legitimate records ($N = 99,870$): 99,870 start with `"M"`, 0 start with `"C"`.
  - Fraud records ($N = 130$): 130 start with `"C"`, 0 start with `"M"`.
* **Impact:** While `RAW_FEATURE_COLUMNS` intentionally excludes `nameDest` to prevent ID memorization, this demonstrates that the synthetic generator enforced absolute artificial separation between classes across all attributes.

### Bug 4: Inference vs Training Feature Contract Mismatch on `step`
* **Location:** `api/index.py` (line 397) vs `src/preprocessing.py` (line 55, 95, 404).
* **Mechanism:**
  - During training, `step` represents the elapsed simulation hour ($1 \le \text{step} \le 744$, covering 31 days). The fitted `StandardScaler` in `ColumnTransformer` recorded:
    $$\mu_{\text{step}} = 371.51, \quad \sigma_{\text{step}} = 214.74$$
  - In `api/index.py`, line 397 constructs the inference payload as:
    ```python
    raw_input = pd.DataFrame([{
        "step": transaction.hour_of_day,  # Provided as an integer between 0 and 23
        ...
    }])
    ```
  - During `preprocessor.transform(raw_input)`:
    1. `step` is standardized using the training parameters:
       $$z_{\text{step}} = \frac{\text{hour\_of\_day} - 371.51}{214.74} \in [-1.73, -1.62]$$
    2. `PaySimFeatureEngineer` calculates:
       $$\text{hour\_of\_day} = \text{step} \pmod{24}$$
       Because `step` was passed as `hour_of_day`, it performs `hour_of_day % 24`, which is redundant.
* **Impact:** At inference time, the model receives a standardized `step` value that is permanently stuck at $\approx -1.7$ standard deviations, violating the distribution seen during training.

### Bug 5: Optimization Warnings Due to Perfect Linear Separability
* **Location:** `src/train_model.py` (line 122–126) and `api/index.py` (lines 177–192).
* **Mechanism:**
  - Because `errorBalanceDest` and `errorBalanceOrig` provide complete linear separation, the maximum likelihood estimate for Logistic Regression coefficients approaches $\pm \infty$.
  - The standard `lbfgs` solver encounters severe floating-point overflow and divide-by-zero conditions when computing sigmoid gradients.
  - While `train_model.py` switched to `solver="liblinear"`, `api/index.py` still contains suppression filters for runtime `matmul` status warnings emitted during matrix operations on extreme coefficient weights.

---

## 4. Potential Problems & Architectural Deficiencies

### Potential Problem 1: Absence of a Baseline Classifier
The current pipeline evaluates Logistic Regression, Random Forest, and Histogram Gradient Boosting, but omits a `DummyClassifier` baseline. On a dataset with 99.87% majority class prevalence, a dummy model that always predicts class 0 achieves:
- Accuracy: **99.87%**
- Recall: **0.0%**
- Precision: **0.0%**
- PR-AUC: **0.0013** (equal to the base positive class prevalence)
- ROC-AUC: **0.5000**

Without displaying this baseline, non-technical stakeholders may misinterpret high accuracy as evidence of model effectiveness.

### Potential Problem 2: Small Positive Sample Size in Evaluation ($N = 26$)
In both the inner validation split and outer holdout split, only 26 fraudulent transactions exist. 
- A single false negative changes the recall score by:
  $$\Delta \text{Recall} = \frac{1}{26} \approx 3.85\%$$
- A point estimate of 100% recall on 26 examples is statistically fragile. Without bootstrap confidence intervals (e.g. 95% CI), uncertainty is completely obscured.

### Potential Problem 3: Reliance on ROC-AUC for Imbalanced Data
ROC-AUC evaluates False Positive Rate ($\text{FPR} = \frac{\text{FP}}{\text{FP} + \text{TN}}$). Because $\text{TN} = 19,974$, adding 100 false positives produces an FPR of only $0.5\%$, keeping ROC-AUC $> 0.99$. In contrast, PR-AUC directly captures the drop in Precision ($\frac{\text{TP}}{\text{TP} + \text{FP}}$). PR-AUC and FPR must be reported alongside ROC-AUC.

### Potential Problem 4: Domain Gap Between PaySim Features and Live UPI Protocols
The PaySim schema assumes that transaction records contain sender and receiver account balances before and after each transaction (`oldbalanceOrg`, `newbalanceOrig`, `oldbalanceDest`, `newbalanceDest`).
In real-world UPI networks (NPCI / PSPs / Payment Gateways like Razorpay):
- Merchant integrations receive only `payment_id`, `order_id`, `amount`, `vpa`, `email`, `contact`, and `status`.
- Core banking account balances are private, encrypted banking data never transmitted to merchant checkout APIs.
- The model cannot be deployed on real gateway webhooks without an intermediate banking data aggregation layer.

---

## 5. Sample Distribution & Split Verification

The exact counts of legitimate and fraudulent records across all splits were verified:

| Partition | Total Rows | Legitimate (0) | Fraud (1) | Fraud Rate | Resampling Applied? |
|---|---|---|---|---|---|
| **Full Raw Dataset** (`transactions.csv`) | 100,000 | 99,870 | 130 | 0.1300% | None |
| **Development Partition** (80% of Full) | 80,000 | 79,896 | 104 | 0.1300% | None |
| **Outer Holdout Test Partition** (20% of Full) | 20,000 | 19,974 | 26 | 0.1300% | **None (Untouched)** |
| **Selection Train Partition** (75% of Dev) | 60,000 | 59,922 | 78 | 0.1300% | Raw: None |
| **Selection Train (Post-SMOTENC)** | 119,844 | 59,922 | 59,922 | 50.0000% | SMOTENC (5 neighbors) |
| **Selection Validation Partition** (25% of Dev) | 20,000 | 19,974 | 26 | 0.1300% | **None (Untouched)** |
| **Final Development (Post-SMOTENC)** | 159,792 | 79,896 | 79,896 | 50.0000% | SMOTENC (5 neighbors) |

### Verification of Displayed Splits:
- **Top Summary Cards & Confusion Matrix on Dashboard:** Evaluated on the **Outer Holdout Test Partition** ($N = 20,000$; 19,974 legit, 26 fraud), recomputed dynamically by `/api/performance`.
- **Model Comparison Table on Dashboard:** Displays the **Selection Validation Partition** ($N = 20,000$; 19,974 legit, 26 fraud), retrieved from `_META["comparison"]`.
- **Duplicate Records Check:** Verified exactly **0 duplicate rows** in `data/transactions.csv`.

---

## 6. Non-Bugs & Valid Architectural Implementations

The audit confirmed several strong engineering practices in the existing codebase:
1. **No Resampling Leakage:** SMOTENC is strictly confined to training sets (`X_selection_train` and `X_development`). Validation and outer holdout sets are evaluated on their natural, un-oversampled class distributions (0.13% fraud).
2. **Leakage-Free Feature Scaling:** The `high_value_threshold_` in `PaySimFeatureEngineer` and `StandardScaler` statistics are fitted strictly on training data and reused during evaluation.
3. **Atomic File Serialization:** `train_model.py` uses temporary files and `os.replace` to write artifacts atomically, preventing corrupted model artifacts during interruptions.
4. **Transparent Metadata Provenance:** `infer_dataset_provenance()` computes a SHA-256 hash of `transactions.csv` and records clear evaluation caveats in `model_meta.json`.

---

## 7. Baseline & Model Evaluation Comparison

The table below contrasts the current models against a naive baseline and the deterministic single-feature heuristic rule on the **outer holdout test partition** (20,000 samples; 19,974 legitimate, 26 fraud):

| Model / Strategy | Accuracy | Precision | Recall | F1-Score | ROC-AUC | PR-AUC | False Positive Rate (FPR) | Confusion Matrix (TN, FP, FN, TP) |
|---|---|---|---|---|---|---|---|---|
| **DummyClassifier** (`most_frequent`) | 99.87% | 0.00% | 0.00% | 0.0000 | 0.5000 | 0.0013 | **0.0000%** | TN=19,974, FP=0, FN=26, TP=0 |
| **Single Rule:** `errorBalanceDest > 1.0` | 100.00% | 100.00% | 100.00% | 1.0000 | 1.0000 | 1.0000 | **0.0000%** | TN=19,974, FP=0, FN=0, TP=26 |
| **Logistic Regression** (Current Saved) | 100.00% | 100.00% | 100.00% | 1.0000 | 1.0000 | 1.0000 | **0.0000%** | TN=19,974, FP=0, FN=0, TP=26 |
| **Random Forest** | 100.00% | 100.00% | 100.00% | 1.0000 | 1.0000 | 1.0000 | **0.0000%** | TN=19,974, FP=0, FN=0, TP=26 |
| **Histogram Gradient Boosting** | 99.995% | 100.00% | 96.15% | 0.9804 | 1.0000 | 1.0000 | **0.0000%** | TN=19,974, FP=0, FN=1, TP=25 |

---

## 8. Defensible Evaluation & Remediation Recommendations

To transform this academic prototype into an authentic, defensible machine learning pipeline, the following staged fixes are recommended:

### Phase 1: Correct Synthetic Generator Target Leakage (`generate_data.py`)
1. **Introduce Stochastic Accounting Noise:** In real banking systems, balance reconciliations are imperfect due to pending holds, delayed settlement fees, cashback, and asynchronous ledger updates.
   - For legitimate transactions: Introduce non-zero variance in balance updates:
     $$\text{new\_dest} = \text{old\_dest} + \text{amount} + \mathcal{N}(0, \sigma^2)$$
   - For fraudulent transactions: Add realistic variation so fraud does not always perfectly drain or freeze accounts.
2. **Mix Customer and Merchant Destinations:** Legitimate transactions must include peer-to-peer transfers (customer to customer), and fraud must include rogue merchant accounts.
3. **Distribution Overlap:** Ensure fraudulent transaction amounts and timing overlap realistically with legitimate high-value transactions.

### Phase 2: Fix Inference Feature Contract (`api/index.py`)
1. Modify `api/index.py` (line 397):
   - Separate simulation `step` from `hour_of_day`.
   - Allow callers to pass `hour_of_day`, and calculate `step` consistently or set a default simulation step that matches the training distribution mean.

### Phase 4: Retrain and Validate
1. Re-run data generation and model training to produce authentic, non-leaking artifacts.
2. Verify all API routes and unit test assertions.

---

## 9. Remediation & Implementation Verification Results

The proposed remediation was implemented and verified across the pipeline:

### 1. Data Generation Target Leakage Eliminated (`generate_data.py`)
- Regenerated 100,000 transactions (99,870 legitimate, 130 fraud) with stochastic balance updates, delayed settlements, unrecorded merchant balances (`old_dest=0, new_dest=0`), and mixed `M`/`C` destination prefixes.
- **Verification:** The naive decision rule `errorBalanceDest > 1.0` collapsed from 100% precision down to **0.11% precision** (identical to random guessing), confirming that the deterministic leakage shortcut has been completely eliminated.

### 2. Verified Model Comparison (Validation Partition)
With genuine variation present, model performance reflects authentic machine-learning discrimination:

| Model | Recall | Precision | F1-Score | PR-AUC | ROC-AUC | FPR | Accuracy |
|---|---|---|---|---|---|---|---|
| **Dummy Classifier** (Baseline) | 0.00% | 0.00% | 0.0000 | 0.0013 | 0.5000 | 0.0000% | 99.87% |
| **Logistic Regression** | 100.00% | 5.83% | 0.1102 | 0.1723 | 0.9941 | 2.1027% | 97.90% |
| **Random Forest** | 92.31% | 27.27% | 0.4211 | 0.6243 | 0.9992 | 0.3204% | 99.67% |
| **Histogram Gradient Boosting** (Winner) | **96.15%** | **48.08%** | **0.6410** | **0.8730** | **0.9998** | **0.1352%** | **99.86%** |

### 3. Final Model Evaluation on Untouched Holdout Test Partition
Evaluated once on the 20,000-sample test partition (19,974 legitimate, 26 fraud):
- **Selected Model:** `Histogram Gradient Boosting`
- **Recall:** **88.46%** (23 / 26 true frauds caught)
- **Precision:** **50.00%** (23 true alerts, 23 false alarms out of 19,974 legitimate transactions)
- **F1 Score:** **0.6389**
- **PR-AUC:** **0.8446**
- **ROC-AUC:** **0.9995**
- **False Positive Rate:** **0.001151** (0.115% false alarm rate)
- **Confusion Matrix:** $\text{TN}=19,951, \text{FP}=23, \text{FN}=3, \text{TP}=23$

### 4. 95% Bootstrap Confidence Intervals (1,000 Resamples)
- **Recall:** Median: 0.8846 (95% CI: `[0.7692, 1.0000]`)
- **Precision:** Median: 0.5000 (95% CI: `[0.4067, 0.6216]`)
- **F1 Score:** Median: 0.6389 (95% CI: `[0.5429, 0.7463]`)
- **PR-AUC:** Median: 0.8504 (95% CI: `[0.7407, 0.9397]`)
- **ROC-AUC:** Median: 0.9996 (95% CI: `[0.9991, 0.9999]`)

### 5. API & Inference Verification
- Fixed `step` contract in `api/index.py` (line 397).
- Updated `/api/performance` to serve `pr_auc`, `false_positive_rate`, and `bootstrap_ci`.
- All 12 unit tests pass cleanly (`Ran 12 tests in 0.101s, OK`).

