# UPI-Style Fraud Detection with Machine Learning

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#run-locally)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](#api-endpoints)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-000000?logo=nextdotjs&logoColor=white)](#architecture)
[![Status](https://img.shields.io/badge/Status-Educational%20prototype-F59E0B)](#current-data-status--read-before-presenting-results)

A B.Tech capstone prototype that scores a digital-payment transaction as likely
legitimate or potentially fraudulent. A FastAPI service loads a saved
scikit-learn model, and a Next.js dashboard displays instant transaction-level
predictions, dataset analysis, and model evaluation.

> **Scope:** This is an educational prototype for UPI-*style* fraud detection.
> It is not connected to NPCI, any bank, or the live UPI network, and it is not
> real-time payment-network infrastructure.

## Live demo

- **Dashboard:** [upi-fraud-detection-ml.vercel.app](https://upi-fraud-detection-ml.vercel.app)
- **Inference API:** [upi-fraud-detection-api.vercel.app](https://upi-fraud-detection-api.vercel.app)
- **API health:** [upi-fraud-detection-api.vercel.app/api/health](https://upi-fraud-detection-api.vercel.app/api/health)

The public demo uses two separate Vercel projects: a Next.js frontend and a
FastAPI inference API. PostgreSQL/Neon is **not configured** on the current
public demo, so predictions are still scored normally but are not retained in
the transaction-history table.

## Contents

- [Live demo](#live-demo)
- [Data provenance and scope](#current-data-status--read-before-presenting-results)
- [Architecture](#architecture)
- [Highlights](#what-is-built)
- [Local setup](#run-locally)
- [API reference](#api-endpoints)
- [Model workflow](#model-workflow-and-viva-points)
- [Testing](#testing-and-quality-checks)
- [Configuration](#configuration-and-persistence)
- [Deployment](#deployment)
- [Security, contributing, and roadmap](#security-and-responsible-use)

## Current data status — read before presenting results

The checked-in [`data/transactions.csv`](data/transactions.csv) is a
**project-local synthetic PaySim-like development fixture** produced by
[`generate_data.py`](generate_data.py). It contains 100,000 rows and 130
fraud-labelled rows (0.13%). It is useful for exercising the full application
locally, but it is **not a public bank, NPCI, or real UPI dataset**. Its
amounts are synthetic/nominal values; the UI formats them as INR only for a
familiar UPI-style demo presentation.

The training script fingerprints this fixture and saves that fact in
[`models/model_meta.json`](models/model_meta.json). Its currently perfect
development metrics must not be presented as real-world validation; the
synthetic generator makes at least one balance-mismatch pattern artificially
easy to learn.

Before a final report or viva, replace
[`data/transactions.csv`](data/transactions.csv) with a documented public
digital-payments dataset, then retrain. The running API deliberately reads
that path for both dashboard summaries and held-out performance evaluation, so
training from a different file without replacing it would make the UI and
saved artifacts inconsistent.

The replacement CSV must contain the binary target `isFraud` and these
PaySim-style source columns: `step`, `type`, `amount`,
`oldbalanceOrg`, `newbalanceOrig`, `oldbalanceDest`, and
`newbalanceDest`. Values must be finite; amount must be positive; balances
must be non-negative; both target classes need at least six records. Extra ID
columns are allowed but intentionally ignored.

~~~bash
cp path/to/public_payments.csv data/transactions.csv
python src/train_model.py --dataset-kind public --dataset-source "Dataset name and source URL"
~~~

Do not describe either dataset as real UPI transaction logs. The defensible
description is: *“a public digital-payments dataset used to develop a prototype
for UPI-style fraud detection.”*

## Architecture

```mermaid
flowchart LR
  U[User] --> N[Next.js frontend (Vercel project: frontend)]
  N -->|HTTPS JSON| A[FastAPI inference API (Vercel project: repository root)]
  A --> M[Saved model + preprocessing pipeline]
  A -->|optional prediction history| P[(Neon Postgres)]
  D[Documented digital-payments dataset] --> T[Training pipeline]
  T --> M
```

The frontend never loads or retrains the model. The API applies the exact
saved preprocessing object used in training, then returns a probability,
label, and risk band. The current public deployment uses two independent
Vercel projects; the frontend calls the API over HTTPS.

## What is built

- Leakage-safe feature engineering inside a reusable sklearn preprocessing
  pipeline.
- Logistic Regression, Random Forest, and Histogram Gradient Boosting model
  comparison.
- Stratified development/validation/holdout workflow with **SMOTENC only on
  training partitions**.
- Precision, recall, F1, PR-AUC, and ROC-AUC evaluation; accuracy is shown
  only for completeness.
- FastAPI endpoints for prediction, live dashboard statistics, model
  performance, CSV analysis, and optional prediction history.
- Next.js pages for Dashboard, Transaction Prediction, Dataset Analysis,
  Model Performance, and About.
- Optional durable prediction history in Neon/PostgreSQL via `DATABASE_URL`.

## Project structure

```text
.
├── api/
│   ├── main.py                 # FastAPI entry point
│   ├── index.py                # API routes and saved-artifact inference
│   ├── database.py             # Optional Neon/PostgreSQL history
│   └── requirements.txt
├── data/
│   └── transactions.csv        # Synthetic development fixture by default
├── frontend/                   # Next.js App Router application
├── models/
│   ├── fraud_model.pkl
│   ├── preprocessor.pkl
│   ├── model_meta.json
│   └── feature_importances.csv
├── src/
│   ├── preprocessing.py
│   └── train_model.py
├── tests/                     # FastAPI contract checks
├── .env.example
├── generate_data.py
└── render.yaml
```

Legacy Streamlit/Stitch helper files remain in the repository as earlier
prototype material. They are not part of the deployed Next.js + FastAPI
architecture described above.

## Run locally

**Recommended runtime:** Python 3.12 and Node.js 18.17+ (Node 20/22 LTS is a
good choice). The checked-in artifacts and Render configuration use Python
3.12. The current Python dependencies also run on Python 3.9+, but retraining
and deployment should use the same Python 3.12 environment for reproducibility.

### 1. Create the Python environment and train artifacts

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/train_model.py
```

On Windows PowerShell, use `py -3.12 -m venv .venv` and then
`.\.venv\Scripts\Activate.ps1`.

The training script saves a single model plus the exact fitted preprocessing
pipeline. The inference API never retrains a model.

### 2. Start FastAPI

```bash
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Check readiness at <http://localhost:8000/api/health>. The automatic API docs
are at <http://localhost:8000/docs>.

### 3. Start the Next.js frontend

Copy `frontend/.env.example` to `frontend/.env.local` (or create it) with:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Then run:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:3000>.

### 4. Verify the local integration

1. Confirm the health endpoint reports `status: "ok"`, with model,
   preprocessor, and dataset all loaded.
2. On the Dashboard, confirm the KPI cards and charts load rather than the
   API-unavailable state.
3. On **Transaction Prediction**, submit the provided sample values and confirm
   a probability, prediction, and risk band are shown.

If the frontend shows an API-unavailable message, make sure both processes are
running, that `NEXT_PUBLIC_API_URL` is exactly
`http://localhost:8000`, and that the browser address is either
`localhost:3000` or `127.0.0.1:3000`. Both origins are accepted by the
local API default. Restart the Next.js development server after changing a
`NEXT_PUBLIC_` variable.

## API endpoints

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Artifact and optional database readiness |
| `GET` | `/api/dataset-info` | Dataset schema and provenance |
| `GET` | `/api/stats` | Dashboard KPIs computed from the loaded dataset |
| `POST` | `/api/predict` | Instant transaction-level prediction |
| `GET` | `/api/predictions?limit=1..100` | Recent Postgres-backed predictions, if configured |
| `GET` | `/api/charts/fraud-by-type` | Chart-ready fraud counts by transaction type |
| `GET` | `/api/charts/fraud-by-hour` | Chart-ready fraud rate by hour |
| `GET` | `/api/charts/amount-distribution` | Label-separated amount summary |
| `GET` | `/api/performance` | Saved-model metrics, ROC data, and feature importance |
| `POST` | `/api/analyse-csv` | Basic EDA for an uploaded CSV (20 MB maximum); does not retrain the model |

Example request:

```bash
curl -X POST http://localhost:8000/api/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "amount": 1000,
    "transaction_type": "PAYMENT",
    "hour_of_day": 12,
    "old_balance_orig": 5000,
    "new_balance_orig": 4000,
    "old_balance_dest": 1000,
    "new_balance_dest": 2000
  }'
```

Example response shape:

```json
{
  "prediction": "LEGITIMATE",
  "fraud_probability": 0.001234,
  "risk_level": "LOW",
  "error_balance_orig": 0.0,
  "error_balance_dest": 0.0,
  "is_high_value": false,
  "saved_to_history": false
}
```

Supported transaction types are `PAYMENT`, `TRANSFER`, `CASH_OUT`,
`CASH_IN`, and `DEBIT`; input is normalized to uppercase. Amount must be
positive, balances must be non-negative, and `hour_of_day` must be from 0
through 23. Invalid input returns HTTP 422. Missing artifacts or an invalid
active dataset returns HTTP 503. The `LOW`, `MEDIUM`, and `HIGH` risk
bands are interface-level probability bands, not bank-standard fraud scores.

## Model workflow and viva points

1. Split data with `stratify=y` into a held-out test partition and a separate
   development partition.
2. Use a stratified validation split inside development data for model choice.
3. Apply SMOTENC **only** to each model's training data; validation and
   holdout rows remain untouched.
4. Fit feature engineering, the high-value threshold, scaler, and encoder only
   on training rows.
5. Select a model using recall-first validation evidence, then evaluate the
   winner once on the untouched holdout.

The reusable preprocessing pipeline derives hour of day, a training-fitted
high-value flag, origin-balance mismatch, destination-balance mismatch, and
one-hot transaction type features. Account identifiers are intentionally
excluded because their high cardinality encourages memorisation instead of
generalizable behavior.

Why accuracy is not the headline: on a 0.13% fraud dataset, predicting every
record as legitimate can be approximately 99.87% accurate while detecting no
fraud. Recall answers “how much actual fraud did we catch?”, while precision
answers “how often was a fraud alert correct?” In this prototype, recall is
weighted more heavily because missing fraud is costlier than manually reviewing
some legitimate transactions.

The saved model currently uses a 0.5 decision threshold. `LOW`, `MEDIUM`, and
`HIGH` risk bands are interface-level probability bands, not bank-standard
fraud scores.

## Testing and quality checks

Run the backend contract suite from the repository root after activating the
Python environment:

```bash
python -m unittest discover -s tests -v
```

Run the frontend static checks and production build:

```bash
cd frontend
npm run lint
npm run build
```

The backend tests verify artifact readiness, raw prediction input validation,
live dashboard route data, and that CSV analysis stays separate from model
training.

## Configuration and persistence

Copy [`.env.example`](.env.example) values into your deployment environment;
never commit a real connection string. Set `DATABASE_URL` on the FastAPI
service to a Neon PostgreSQL connection string. On startup, the service creates
the `predictions` table if it does not already exist. Without this variable,
prediction works normally but history stays empty.

| Variable | Service | Required | Purpose |
| --- | --- | --- | --- |
| `ALLOWED_ORIGINS` | FastAPI | No | Comma-separated browser origins allowed by CORS |
| `DATABASE_URL` | FastAPI | No | Neon/PostgreSQL connection string for durable history |
| `NEXT_PUBLIC_API_URL` | Next.js | Yes in production | Public HTTPS base URL of the FastAPI service |

### Current Vercel environment configuration

Set these values in the Vercel project dashboards; do not commit them to a
repository file:

```dotenv
# Frontend Vercel project (Root Directory: frontend)
NEXT_PUBLIC_API_URL=https://upi-fraud-detection-api.vercel.app

# FastAPI Vercel project (Root Directory: repository root)
ALLOWED_ORIGINS=https://upi-fraud-detection-ml.vercel.app
```

`NEXT_PUBLIC_API_URL` is intentionally public: Next.js embeds it in the
browser bundle at build time. Redeploy the frontend after changing it. In
contrast, `ALLOWED_ORIGINS` and an optional `DATABASE_URL` belong only to the
FastAPI project. Use a comma-separated `ALLOWED_ORIGINS` value if more than
one frontend origin must be accepted.

`DATABASE_URL` is deliberately unset for the current public demo. Configure it
only on the FastAPI project when durable prediction history is required; until
then, `/api/predictions` returns no stored history and prediction responses set
`saved_to_history` to `false`.

## Deployment

### Current public deployment → Vercel

| Project | Public URL | Root Directory | Runtime |
| --- | --- | --- | --- |
| Frontend | [upi-fraud-detection-ml.vercel.app](https://upi-fraud-detection-ml.vercel.app) | `frontend` | Next.js |
| Inference API | [upi-fraud-detection-api.vercel.app](https://upi-fraud-detection-api.vercel.app) | repository root | FastAPI |

Both projects deploy from the same repository, but they must remain separate:
the frontend contains the browser UI and the root-level API deployment needs
access to the saved `models/` artifacts and `data/transactions.csv`. Keep
those files available in the API deployment.

Vercel’s documented monorepo workflow supports deploying a subdirectory as a
separate project; using `frontend` as the frontend root keeps the ML inference
service independent of the browser build. [Vercel monorepo documentation](https://vercel.com/docs/monorepos)

### Alternative API hosting → Render

The included [`render.yaml`](render.yaml) starts `uvicorn api.main:app` from
the repository root. Render remains an optional alternative if the API is
moved off Vercel. In that case, set the frontend's `NEXT_PUBLIC_API_URL` to the
Render HTTPS URL, redeploy the frontend, and set Render's `ALLOWED_ORIGINS` to
the frontend URL. Keep `data/` and `models/` artifacts available to the
service.

## Security and responsible use

- Never commit database URLs, tokens, or real environment files. In particular,
  `NEXT_PUBLIC_*` values are bundled into client-side JavaScript and must
  never contain secrets. Keep `DATABASE_URL` on the server only.
- CORS limits browser origins; it is **not authentication**. The prototype has
  no authentication, authorization, rate limiting, monitoring, audit trail, or
  human-review workflow.
- The CSV analysis endpoint reads uploads into API memory and caps them at
  20 MB. It does not store the uploaded file or retrain the model.
- Do not upload, commit, or train on personal, bank, or real payment data
  without explicit authorization and an approved data-governance process.
- Never use the risk output to approve, reject, block, or investigate a real
  person's payment.

## Contributing

Once this repository is shared, contributions should follow a small,
reviewable workflow:

1. Create a focused branch from `main`.
2. Keep model, data-provenance, and evaluation claims evidence-based.
3. Run the backend and frontend checks listed above.
4. Document dataset source, class distribution, split strategy, and
   precision/recall/F1/ROC-AUC whenever training behavior changes.
5. Do not commit secrets, real payment data, node_modules, virtual
   environments, or generated build output.

## Roadmap

- [ ] Replace the synthetic fixture with a documented public digital-payments
  dataset, retrain, and record the actual holdout metrics.
- [ ] Configure Neon PostgreSQL if durable prediction history is required.
- [x] Deploy the FastAPI service and Next.js frontend as separate Vercel
  projects and configure their production cross-origin URLs.
- [ ] Add authentication, rate limiting, monitoring, and a human-review design
  only if the scope expands beyond a supervised capstone demonstration.

## License

No license has been selected yet. Add an appropriate LICENSE file before making
the repository publicly reusable.
