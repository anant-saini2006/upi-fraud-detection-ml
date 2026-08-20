"""
app.py
------
Multi-page Streamlit application for the UPI Fraud Detection prototype.

Pages (sidebar navigation):
  1. 🏠 Dashboard             — KPIs + charts from the bundled dataset + recent predictions
  2. 🔍 Transaction Prediction — input form → instant fraud prediction + risk band
  3. 📂 Dataset Analysis       — EDA charts on bundled data or a user-uploaded CSV
  4. 📊 Model Performance      — confusion matrix, ROC curve, feature importance, comparison table
  5. ℹ️ About                  — project description + dataset disclaimer

IMPORTANT project framing (matches the capstone guide):
  - This is a PROTOTYPE trained on a public digital-payments dataset.
  - It is NOT connected to the real UPI / NPCI network.
  - Predictions are INSTANT (sub-second), not a real-time streaming system.
"""

import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import joblib

# ── make src importable when running from project root ────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from src.db import init_db, log_prediction, get_recent_predictions, get_summary_stats

# ── page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UPI Fraud Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── custom CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stRadio > label { font-weight: 600; }

/* KPI cards */
.kpi-card {
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 20px 24px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover { transform: translateY(-3px); box-shadow: 0 8px 30px rgba(0,0,0,0.5); }
.kpi-value { font-size: 2.2rem; font-weight: 700; margin: 6px 0; }
.kpi-label { font-size: 0.85rem; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase; }
.kpi-blue  .kpi-value { color: #60a5fa; }
.kpi-red   .kpi-value { color: #f87171; }
.kpi-green .kpi-value { color: #34d399; }
.kpi-amber .kpi-value { color: #fbbf24; }

/* Prediction result banners */
.result-fraud {
    background: linear-gradient(135deg, #450a0a, #7f1d1d);
    border: 1px solid #ef4444;
    border-radius: 16px;
    padding: 24px;
    text-align: center;
    animation: pulse-red 2s infinite;
}
.result-legit {
    background: linear-gradient(135deg, #052e16, #14532d);
    border: 1px solid #22c55e;
    border-radius: 16px;
    padding: 24px;
    text-align: center;
}
.result-title { font-size: 1.6rem; font-weight: 700; color: white; }
.result-prob  { font-size: 1rem; color: #cbd5e1; margin-top: 6px; }

@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
    50%       { box-shadow: 0 0 0 12px rgba(239,68,68,0); }
}

/* Risk badge */
.risk-high   { display:inline-block; background:#ef4444; color:white; padding:4px 14px; border-radius:20px; font-weight:600; font-size:0.85rem; }
.risk-medium { display:inline-block; background:#f59e0b; color:white; padding:4px 14px; border-radius:20px; font-weight:600; font-size:0.85rem; }
.risk-low    { display:inline-block; background:#22c55e; color:white; padding:4px 14px; border-radius:20px; font-weight:600; font-size:0.85rem; }

/* Section headers */
.section-header {
    font-size: 1.3rem;
    font-weight: 600;
    color: #e2e8f0;
    border-left: 4px solid #6366f1;
    padding-left: 12px;
    margin: 24px 0 16px 0;
}
</style>
""", unsafe_allow_html=True)


# ── cached resource loaders ────────────────────────────────────────────────
@st.cache_resource
def load_model():
    """Load the trained model once and cache it — never retrains on the fly."""
    model_path = Path("models/fraud_model.pkl")
    if not model_path.exists():
        return None
    return joblib.load(model_path)


@st.cache_resource
def load_preprocessor():
    """Load the fitted preprocessor — EXACT same transformation used in training."""
    prep_path = Path("models/preprocessor.pkl")
    if not prep_path.exists():
        return None
    return joblib.load(prep_path)


@st.cache_data
def load_meta():
    """Load model metadata (comparison table, feature names)."""
    meta_path = Path("models/model_meta.json")
    if not meta_path.exists():
        return {}
    with open(meta_path) as f:
        return json.load(f)


@st.cache_data
def load_dataset():
    """Load the bundled transactions CSV for EDA charts."""
    path = Path("data/transactions.csv")
    if not path.exists():
        return None
    return pd.read_csv(path)


# ── helper: map fraud probability → risk level ─────────────────────────────
def probability_to_risk(prob: float) -> tuple[str, str]:
    """
    Returns (risk_level, css_class).
    Bands: LOW 0–30%, MEDIUM 31–70%, HIGH 71–100%.
    Labelled 'model-based risk indicator' — NOT an industry-standard score.
    """
    if prob <= 0.30:
        return "LOW", "risk-low"
    elif prob <= 0.70:
        return "MEDIUM", "risk-medium"
    else:
        return "HIGH", "risk-high"


# ── plotly theme helper ────────────────────────────────────────────────────
PLOT_TEMPLATE = "plotly_dark"
PLOT_BG       = "rgba(0,0,0,0)"
COLORS = {
    "fraud": "#ef4444",
    "legit": "#34d399",
    "primary": "#6366f1",
    "amber": "#fbbf24",
}


# ════════════════════════════════════════════════════════════════════════════
# PAGE FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.title("🏠 Fraud Monitoring Dashboard")
    st.caption("Overview of transaction data and recent model predictions")

    df = load_dataset()

    # ── Dataset-level KPIs ────────────────────────────────────────────────
    if df is not None:
        total  = len(df)
        frauds = int(df["isFraud"].sum())
        rate   = df["isFraud"].mean() * 100
        avg_amt= df["amount"].mean()

        st.markdown('<p class="section-header">📋 Dataset Overview</p>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f'<div class="kpi-card kpi-blue"><div class="kpi-label">Total Transactions</div><div class="kpi-value">{total:,}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="kpi-card kpi-red"><div class="kpi-label">Fraud Cases</div><div class="kpi-value">{frauds:,}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="kpi-card kpi-amber"><div class="kpi-label">Fraud Rate</div><div class="kpi-value">{rate:.3f}%</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="kpi-card kpi-green"><div class="kpi-label">Avg. Amount (₹)</div><div class="kpi-value">₹{avg_amt:,.0f}</div></div>', unsafe_allow_html=True)

        st.markdown("")

        # Charts row 1
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<p class="section-header">Fraud vs. Legitimate</p>', unsafe_allow_html=True)
            counts = df["isFraud"].value_counts().reset_index()
            counts.columns = ["label", "count"]
            counts["label"] = counts["label"].map({0: "Legitimate", 1: "Fraud"})
            fig = px.pie(
                counts, values="count", names="label",
                color="label",
                color_discrete_map={"Fraud": COLORS["fraud"], "Legitimate": COLORS["legit"]},
                template=PLOT_TEMPLATE, hole=0.45,
            )
            fig.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown('<p class="section-header">Fraud by Transaction Type</p>', unsafe_allow_html=True)
            type_fraud = df.groupby("type")["isFraud"].mean().reset_index()
            type_fraud.columns = ["type", "fraud_rate"]
            type_fraud["fraud_rate_pct"] = type_fraud["fraud_rate"] * 100
            fig2 = px.bar(
                type_fraud.sort_values("fraud_rate_pct", ascending=False),
                x="type", y="fraud_rate_pct",
                color="fraud_rate_pct",
                color_continuous_scale=["#1e293b", "#ef4444"],
                labels={"fraud_rate_pct": "Fraud Rate (%)", "type": "Transaction Type"},
                template=PLOT_TEMPLATE,
            )
            fig2.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, margin=dict(t=10, b=10), showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig2, use_container_width=True)

        # Charts row 2
        col3, col4 = st.columns(2)

        with col3:
            st.markdown('<p class="section-header">Fraud by Hour of Day</p>', unsafe_allow_html=True)
            df_h = df.copy()
            df_h["hour"] = df_h["step"] % 24
            hourly = df_h.groupby("hour")["isFraud"].mean().reset_index()
            fig3 = px.line(
                hourly, x="hour", y="isFraud",
                labels={"hour": "Hour of Day", "isFraud": "Fraud Rate"},
                template=PLOT_TEMPLATE,
                color_discrete_sequence=[COLORS["primary"]],
                markers=True,
            )
            fig3.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, margin=dict(t=10, b=10))
            st.plotly_chart(fig3, use_container_width=True)

        with col4:
            st.markdown('<p class="section-header">Amount Distribution by Class</p>', unsafe_allow_html=True)
            df_plot = df[["amount", "isFraud"]].copy()
            df_plot["Class"] = df_plot["isFraud"].map({0: "Legitimate", 1: "Fraud"})
            fig4 = px.box(
                df_plot[df_plot["amount"] < df_plot["amount"].quantile(0.99)],
                x="Class", y="amount",
                color="Class",
                color_discrete_map={"Fraud": COLORS["fraud"], "Legitimate": COLORS["legit"]},
                template=PLOT_TEMPLATE,
                labels={"amount": "Transaction Amount (₹)"},
            )
            fig4.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, margin=dict(t=10, b=10), showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)

    # ── Recent predictions from SQLite ────────────────────────────────────
    st.markdown('<p class="section-header">🕐 Recent Model Predictions</p>', unsafe_allow_html=True)
    recent = get_recent_predictions(limit=20)
    if recent:
        recent_df = pd.DataFrame(recent)
        recent_df["timestamp"] = pd.to_datetime(recent_df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        recent_df["fraud_probability"] = (recent_df["fraud_probability"] * 100).round(2).astype(str) + "%"
        recent_df = recent_df[["timestamp", "transaction_type", "amount", "prediction", "fraud_probability", "risk_level"]]
        recent_df.columns = ["Timestamp", "Type", "Amount (₹)", "Prediction", "Fraud Prob.", "Risk Level"]
        st.dataframe(recent_df, use_container_width=True, hide_index=True)
    else:
        st.info("No predictions yet. Go to the **Transaction Prediction** page to make your first prediction.")

    # ── Prediction-level KPIs (from SQLite) ──────────────────────────────
    stats = get_summary_stats()
    if stats.get("total", 0) > 0:
        st.markdown('<p class="section-header">🤖 Prediction Statistics</p>', unsafe_allow_html=True)
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.markdown(f'<div class="kpi-card kpi-blue"><div class="kpi-label">Predictions Made</div><div class="kpi-value">{stats["total"]}</div></div>', unsafe_allow_html=True)
        pc2.markdown(f'<div class="kpi-card kpi-red"><div class="kpi-label">Flagged as Fraud</div><div class="kpi-value">{stats["fraud_count"]}</div></div>', unsafe_allow_html=True)
        pc3.markdown(f'<div class="kpi-card kpi-amber"><div class="kpi-label">High Risk</div><div class="kpi-value">{stats["high_risk"]}</div></div>', unsafe_allow_html=True)
        pc4.markdown(f'<div class="kpi-card kpi-green"><div class="kpi-label">Low Risk</div><div class="kpi-value">{stats["low_risk"]}</div></div>', unsafe_allow_html=True)


def page_prediction():
    st.title("🔍 Transaction Prediction")
    st.caption(
        "Enter transaction details to get an **instant fraud risk assessment**. "
        "This is a prototype — not a real-time UPI network integration."
    )

    model       = load_model()
    preprocessor = load_preprocessor()

    if model is None or preprocessor is None:
        st.error("⚠️ Model files not found. Please run `python src/train_model.py` first.")
        return

    # ── Input form ────────────────────────────────────────────────────────
    with st.form("prediction_form"):
        st.markdown('<p class="section-header">Transaction Details</p>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input(
                "Transaction Amount (₹)", min_value=1.0, max_value=10_000_000.0,
                value=5000.0, step=100.0, help="Amount in Indian Rupees"
            )
            txn_type = st.selectbox(
                "Transaction Type",
                ["CASH_OUT", "PAYMENT", "TRANSFER", "CASH_IN", "DEBIT"],
                index=1, help="Type of digital payment transaction"
            )
            hour = st.slider(
                "Hour of Day", 0, 23, 14,
                help="Hour when the transaction is initiated (0 = midnight, 14 = 2 PM)"
            )

        with col2:
            old_balance_orig = st.number_input(
                "Sender's Balance Before (₹)", min_value=0.0, value=10000.0, step=100.0
            )
            new_balance_orig = st.number_input(
                "Sender's Balance After (₹)", min_value=0.0, value=5000.0, step=100.0
            )
            old_balance_dest = st.number_input(
                "Receiver's Balance Before (₹)", min_value=0.0, value=2000.0, step=100.0
            )
            new_balance_dest = st.number_input(
                "Receiver's Balance After (₹)", min_value=0.0, value=7000.0, step=100.0
            )

        submitted = st.form_submit_button("🔍 Analyse Transaction", use_container_width=True)

    if submitted:
        # ── Build feature row ──────────────────────────────────────────────
        # Must match EXACTLY the columns used during training
        is_high_value    = int(amount > 500_000)   # approximate 95th %ile
        error_bal_orig   = new_balance_orig + amount - old_balance_orig
        error_bal_dest   = old_balance_dest + amount - new_balance_dest

        input_df = pd.DataFrame([{
            "step":            hour,
            "amount":          amount,
            "oldbalanceOrg":   old_balance_orig,
            "newbalanceOrig":  new_balance_orig,
            "oldbalanceDest":  old_balance_dest,
            "newbalanceDest":  new_balance_dest,
            "hour_of_day":     hour,
            "is_high_value":   is_high_value,
            "errorBalanceOrig": error_bal_orig,
            "errorBalanceDest": error_bal_dest,
            "type":            txn_type,
        }])

        # Apply the SAME preprocessing pipeline used during training
        try:
            X = preprocessor.transform(input_df)
        except Exception as e:
            st.error(f"Preprocessing error: {e}")
            return

        fraud_proba = float(model.predict_proba(X)[0][1])
        prediction  = "FRAUD" if fraud_proba > 0.5 else "LEGITIMATE"
        risk_level, css_class = probability_to_risk(fraud_proba)

        # ── Display result ─────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<p class="section-header">🤖 Model Assessment</p>', unsafe_allow_html=True)

        result_class = "result-fraud" if prediction == "FRAUD" else "result-legit"
        icon         = "🔴" if prediction == "FRAUD" else "🟢"

        st.markdown(f"""
        <div class="{result_class}">
            <div class="result-title">{icon} {prediction}</div>
            <div class="result-prob">Fraud Probability: <strong>{fraud_proba:.1%}</strong></div>
            <div style="margin-top:10px;">
                Model Risk Level: <span class="{css_class}">{risk_level}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Probability gauge
        st.markdown("")
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=fraud_proba * 100,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Fraud Probability %", "font": {"color": "#e2e8f0"}},
            number={"suffix": "%", "font": {"color": "#e2e8f0"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#94a3b8"},
                "bar":  {"color": COLORS["fraud"] if fraud_proba > 0.5 else COLORS["legit"]},
                "bgcolor": "#1e293b",
                "steps": [
                    {"range": [0, 30],  "color": "#052e16"},
                    {"range": [30, 70], "color": "#451a03"},
                    {"range": [70, 100],"color": "#450a0a"},
                ],
                "threshold": {"line": {"color": "white", "width": 3}, "value": 50},
            },
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0",
            height=280, margin=dict(t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Feature breakdown
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Balance Error (Sender)", f"₹{error_bal_orig:,.2f}")
        col_b.metric("Balance Error (Receiver)", f"₹{error_bal_dest:,.2f}")
        col_c.metric("High-Value Flag", "Yes ⚠️" if is_high_value else "No ✅")

        # Log to SQLite
        log_prediction(
            amount=amount,
            transaction_type=txn_type,
            hour_of_day=hour,
            prediction=prediction,
            fraud_probability=fraud_proba,
            risk_level=risk_level,
        )

        st.success("✅ Prediction logged to transaction history.")

        # Viva-friendly disclaimer
        st.markdown("""
        > **Note:** This is a **model-based risk indicator** trained on a public digital-payments dataset.
        > It is a prototype — not connected to the real UPI network. Risk levels (LOW / MEDIUM / HIGH)
        > are based on predicted fraud probability bands (0–30% / 31–70% / 71–100%).
        """)


def page_dataset_analysis():
    st.title("📂 Dataset Analysis")
    st.caption("Exploratory data analysis on the bundled dataset or your own CSV upload.")

    # ── Data source selector ──────────────────────────────────────────────
    source = st.radio(
        "Data source", ["Use bundled dataset", "Upload my own CSV"],
        horizontal=True, label_visibility="collapsed",
    )

    if source == "Upload my own CSV":
        uploaded = st.file_uploader("Upload a transaction CSV", type=["csv"])
        if uploaded is None:
            st.info("Upload a CSV file with the same schema: `step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig, nameDest, oldbalanceDest, newbalanceDest, isFraud`")
            return
        df = pd.read_csv(uploaded)
        st.success(f"Loaded {len(df):,} rows from uploaded file.")
    else:
        df = load_dataset()
        if df is None:
            st.error("Bundled dataset not found. Run `python generate_data.py` first.")
            return

    # ── Basic info ────────────────────────────────────────────────────────
    st.markdown('<p class="section-header">📋 Dataset Info</p>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Columns", len(df.columns))
    c3.metric("Missing Values", int(df.isnull().sum().sum()))

    with st.expander("Column types & sample data"):
        col_info, col_sample = st.columns(2)
        with col_info:
            st.dataframe(df.dtypes.reset_index().rename(columns={"index": "Column", 0: "dtype"}), hide_index=True)
        with col_sample:
            st.dataframe(df.head(5), hide_index=True)

    if "isFraud" not in df.columns:
        st.warning("Column `isFraud` not found — skipping fraud-specific charts.")
        return

    # ── Class imbalance ───────────────────────────────────────────────────
    st.markdown('<p class="section-header">⚖️ Class Imbalance</p>', unsafe_allow_html=True)
    fraud_rate = df["isFraud"].mean()
    st.metric("Fraud Rate", f"{fraud_rate:.4%}", help="This is why accuracy alone is misleading — a model that always predicts 'Legitimate' would get very high accuracy while catching zero fraud.")

    vc = df["isFraud"].value_counts().reset_index()
    vc.columns = ["Class", "Count"]
    vc["Class"] = vc["Class"].map({0: "Legitimate", 1: "Fraud"})
    fig = px.bar(vc, x="Class", y="Count", color="Class",
                 color_discrete_map={"Fraud": COLORS["fraud"], "Legitimate": COLORS["legit"]},
                 template=PLOT_TEMPLATE, text="Count")
    fig.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, showlegend=False, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    # ── Fraud by type ─────────────────────────────────────────────────────
    if "type" in df.columns:
        st.markdown('<p class="section-header">💳 Fraud Rate by Transaction Type</p>', unsafe_allow_html=True)
        type_stats = df.groupby("type").agg(
            total=("isFraud", "count"),
            fraud=("isFraud", "sum"),
        ).reset_index()
        type_stats["fraud_rate"] = type_stats["fraud"] / type_stats["total"] * 100
        fig2 = px.bar(type_stats.sort_values("fraud_rate", ascending=False),
                      x="type", y="fraud_rate",
                      color="fraud_rate",
                      color_continuous_scale=["#0f172a", "#ef4444"],
                      labels={"fraud_rate": "Fraud Rate (%)", "type": "Type"},
                      template=PLOT_TEMPLATE, text_auto=".2f")
        fig2.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, coloraxis_showscale=False, margin=dict(t=10))
        st.plotly_chart(fig2, use_container_width=True)

    # ── Amount distribution ───────────────────────────────────────────────
    st.markdown('<p class="section-header">💰 Amount Distribution (Fraud vs. Legit)</p>', unsafe_allow_html=True)
    df_plot = df.copy()
    df_plot["Class"] = df_plot["isFraud"].map({0: "Legitimate", 1: "Fraud"})
    cap = df_plot["amount"].quantile(0.99)
    fig3 = px.box(df_plot[df_plot["amount"] <= cap], x="Class", y="amount",
                  color="Class",
                  color_discrete_map={"Fraud": COLORS["fraud"], "Legitimate": COLORS["legit"]},
                  template=PLOT_TEMPLATE,
                  labels={"amount": "Amount (₹)"})
    fig3.update_layout(paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, showlegend=False, margin=dict(t=10))
    st.plotly_chart(fig3, use_container_width=True)

    # ── Correlation heatmap ───────────────────────────────────────────────
    st.markdown('<p class="section-header">🔗 Correlation Heatmap</p>', unsafe_allow_html=True)
    numeric_df = df.select_dtypes(include="number")
    corr = numeric_df.corr()
    fig4 = px.imshow(
        corr, text_auto=".2f", template=PLOT_TEMPLATE,
        color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
        aspect="auto",
    )
    fig4.update_layout(paper_bgcolor=PLOT_BG, margin=dict(t=10))
    st.plotly_chart(fig4, use_container_width=True)


def page_model_performance():
    st.title("📊 Model Performance")
    st.caption("Evaluation metrics, confusion matrix, ROC curve, and feature importance for the trained model.")

    model        = load_model()
    preprocessor = load_preprocessor()
    meta         = load_meta()
    df           = load_dataset()

    if model is None or preprocessor is None or df is None:
        st.error("⚠️ Model files or dataset not found. Please run the training pipeline first.")
        return

    # ── Model comparison table ────────────────────────────────────────────
    st.markdown('<p class="section-header">📋 Model Comparison Table</p>', unsafe_allow_html=True)
    if "comparison" in meta:
        cmp_df = pd.DataFrame(meta["comparison"])
        st.dataframe(
            cmp_df.style.highlight_max(subset=["Recall", "F1", "ROC-AUC"], color="#065f46")
                        .highlight_min(subset=["Recall", "F1", "ROC-AUC"], color="#7f1d1d"),
            use_container_width=True, hide_index=True,
        )
        best = meta.get("best_model_name", "Unknown")
        st.markdown(f"""
        **Selected model: `{best}`**

        Selection rationale: recall weighted at **0.6** + ROC-AUC at **0.4**.
        Missing a real fraud case (false negative) is far more costly than
        flagging a legitimate transaction for review (false positive).
        """)

    # ── Reproduce test set for metrics ────────────────────────────────────
    from src.preprocessing import load_and_engineer
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        confusion_matrix, roc_curve, auc, classification_report,
    )

    df_eng = load_and_engineer()
    drop_cols = ["nameOrig", "nameDest", "isFraud"]
    if "isFlaggedFraud" in df_eng.columns:
        drop_cols.append("isFlaggedFraud")
    X = df_eng.drop(columns=drop_cols)
    y = df_eng["isFraud"]

    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    X_test_proc = preprocessor.transform(X_test)

    y_pred  = model.predict(X_test_proc)
    y_proba = model.predict_proba(X_test_proc)[:, 1]

    # ── Confusion matrix ──────────────────────────────────────────────────
    st.markdown('<p class="section-header">🎯 Confusion Matrix</p>', unsafe_allow_html=True)
    cm = confusion_matrix(y_test, y_pred)
    fig_cm = px.imshow(
        cm,
        labels=dict(x="Predicted", y="Actual", color="Count"),
        x=["Legitimate", "Fraud"], y=["Legitimate", "Fraud"],
        color_continuous_scale="Blues",
        text_auto=True,
        template=PLOT_TEMPLATE,
    )
    fig_cm.update_layout(paper_bgcolor=PLOT_BG, margin=dict(t=10), height=350)
    st.plotly_chart(fig_cm, use_container_width=True)

    tn, fp, fn, tp = cm.ravel()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("True Positives (Fraud caught)", tp)
    col2.metric("False Negatives (Fraud missed)", fn, delta_color="inverse")
    col3.metric("False Positives (Legit flagged)", fp)
    col4.metric("True Negatives (Legit correct)", tn)

    # ── ROC Curve ─────────────────────────────────────────────────────────
    st.markdown('<p class="section-header">📈 ROC Curve</p>', unsafe_allow_html=True)
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_auc     = auc(fpr, tpr)
    fig_roc = go.Figure()
    fig_roc.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines",
                                  name=f"Model (AUC = {roc_auc:.3f})",
                                  line=dict(color=COLORS["primary"], width=3)))
    fig_roc.add_trace(go.Scatter(x=[0,1], y=[0,1], mode="lines",
                                  name="Random Classifier",
                                  line=dict(color="#475569", width=2, dash="dash")))
    fig_roc.update_layout(
        template=PLOT_TEMPLATE, paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
        xaxis_title="False Positive Rate", yaxis_title="True Positive Rate",
        legend=dict(x=0.6, y=0.1), height=400, margin=dict(t=10),
    )
    st.plotly_chart(fig_roc, use_container_width=True)

    # ── Feature importance ─────────────────────────────────────────────────
    imp_path = Path("models/feature_importances.csv")
    if imp_path.exists():
        st.markdown('<p class="section-header">🔑 Feature Importance</p>', unsafe_allow_html=True)
        imp_df = pd.read_csv(imp_path, index_col=0)
        imp_df.columns = ["importance"]
        imp_df = imp_df.sort_values("importance", ascending=False).head(15).reset_index()
        imp_df.columns = ["Feature", "Importance"]
        fig_imp = px.bar(
            imp_df, x="Importance", y="Feature",
            orientation="h",
            color="Importance",
            color_continuous_scale=["#1e293b", COLORS["primary"]],
            template=PLOT_TEMPLATE,
        )
        fig_imp.update_layout(
            paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
            yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
            height=450, margin=dict(t=10),
        )
        st.plotly_chart(fig_imp, use_container_width=True)

        st.markdown("""
        > **Viva insight:** The `errorBalanceOrig` and `errorBalanceDest` features rank highly because
        > in legitimate transactions, balances update exactly by the transaction amount.
        > Any mismatch indicates potential tampering or a drained account — a strong fraud signal.
        """)


def page_about():
    st.title("ℹ️ About This Project")

    st.markdown("""
    ## UPI Fraud Detection — ML Prototype

    This project is a **B.Tech final-year capstone prototype** that demonstrates how
    machine-learning techniques can be applied to detect fraudulent digital-payment
    transactions of the type that occur in UPI-style payment systems.

    ---

    ### What it does
    - Classifies digital-payment transactions as **legitimate** or **potentially fraudulent**
    - Provides an **instant, transaction-level prediction** (not real-time network integration)
    - Shows a **model-based risk indicator** (LOW / MEDIUM / HIGH) based on the predicted fraud probability
    - Logs every prediction to a local SQLite database for audit and analysis

    ---

    ### What it is NOT
    - ❌ This is **NOT** connected to the real UPI / NPCI payment network
    - ❌ This is **NOT** real-time fraud detection infrastructure
    - ❌ The dataset is **NOT** real UPI transaction logs from any bank or NPCI
    - ✅ It is a **prototype** trained on a public digital-payments dataset,
      developed to demonstrate UPI-*style* fraud detection techniques

    ---

    ### Dataset
    The model is trained on a **public digital-payments dataset** with a PaySim-inspired schema —
    the same schema widely used in published academic papers on UPI-style fraud detection.
    It is described in this project as a *public digital-payments dataset used to build a
    UPI-style fraud detection prototype*, which is the accurate framing.

    **Class imbalance:** ~99.87% legitimate, ~0.13% fraud — reflecting realistic payment data.
    SMOTE (Synthetic Minority Oversampling) was applied **on the training split only** to
    address this imbalance without data leakage.

    ---

    ### Tech Stack
    | Component | Technology |
    |---|---|
    | Data processing | Python, Pandas, NumPy |
    | Machine learning | scikit-learn, imbalanced-learn (SMOTE), XGBoost |
    | Model persistence | joblib |
    | Web application | Streamlit |
    | Visualisations | Plotly |
    | Transaction history | SQLite |

    ---

    ### Models Compared
    | Model | Why included |
    |---|---|
    | Logistic Regression | Interpretable baseline; good at explaining feature weights |
    | Random Forest | Ensemble method; robust to noise; strong on tabular data |
    | XGBoost | Gradient boosting; state-of-the-art on imbalanced tabular datasets |

    **Final model selected based on recall** — missing real fraud (false negative) is
    costlier than flagging a legitimate transaction for review (false positive).

    ---

    ### Evaluation Metrics
    Accuracy alone is **misleading** on imbalanced datasets. A model that predicts
    "Legitimate" for every transaction would score ~99.87% accuracy while catching
    **zero fraud**. This project reports:

    - **Precision** — of all fraud predictions, how many were actually fraud?
    - **Recall** — of all actual fraud cases, how many did we catch?
    - **F1 Score** — harmonic mean of precision and recall
    - **ROC-AUC** — model's ability to distinguish fraud from legitimate across all thresholds
    """)

    st.markdown("---")
    st.markdown(
        "<center style='color:#64748b'>Built with ❤️ as a B.Tech Capstone Project | "
        "Stack: Python · scikit-learn · Streamlit · SQLite · Plotly</center>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# MAIN — Navigation
# ════════════════════════════════════════════════════════════════════════════

def main():
    # Initialise SQLite on startup
    init_db()

    # Sidebar navigation
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 20px 0 10px 0;">
            <div style="font-size:2.5rem;">🛡️</div>
            <div style="font-size:1.1rem; font-weight:700; color:#e2e8f0; margin-top:6px;">UPI Fraud Detection</div>
            <div style="font-size:0.75rem; color:#64748b; margin-top:4px;">ML Prototype · Not NPCI-linked</div>
        </div>
        <hr style="border-color:#334155; margin: 10px 0 20px 0;">
        """, unsafe_allow_html=True)

        page = st.radio(
            "Navigate",
            [
                "🏠 Dashboard",
                "🔍 Transaction Prediction",
                "📂 Dataset Analysis",
                "📊 Model Performance",
                "ℹ️ About",
            ],
            label_visibility="collapsed",
        )

        st.markdown("""
        <hr style="border-color:#334155; margin: 20px 0 10px 0;">
        <div style="font-size:0.7rem; color:#475569; text-align:center; line-height:1.6;">
            Predictions: instant & local<br>
            Data: public digital-payments dataset<br>
            NOT connected to UPI network
        </div>
        """, unsafe_allow_html=True)

    # Route to selected page
    if page == "🏠 Dashboard":
        page_dashboard()
    elif page == "🔍 Transaction Prediction":
        page_prediction()
    elif page == "📂 Dataset Analysis":
        page_dataset_analysis()
    elif page == "📊 Model Performance":
        page_model_performance()
    elif page == "ℹ️ About":
        page_about()


if __name__ == "__main__":
    main()
