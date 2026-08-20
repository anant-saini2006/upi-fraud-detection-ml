/**
 * src/lib/api.ts
 * Typed client for the FastAPI backend.
 * All components import from here — single source of truth for API calls.
 */

// In development the FastAPI service normally runs on port 8000. Production
// deployments must set NEXT_PUBLIC_API_URL to the deployed HTTPS API URL.
const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Stats {
  total_transactions: number;
  fraud_count: number;
  legit_count: number;
  fraud_rate: number;
  avg_amount: number;
  max_amount: number;
  model_name: string;
  dataset_source: string;
}

export interface FraudByTypeRow {
  type: string;
  total: number;
  fraud: number;
  fraud_rate: number;
}

export interface FraudByHourRow {
  hour: number;
  fraud_rate: number;
  total: number;
  fraud: number;
}

export interface AmountDistribution {
  display_cap: number;
  legitimate: { min: number; q1: number; median: number; q3: number; max: number; mean: number };
  fraud:      { min: number; q1: number; median: number; q3: number; max: number; mean: number };
}

export interface PredictionInput {
  amount: number;
  transaction_type: string;
  hour_of_day: number;
  old_balance_orig: number;
  new_balance_orig: number;
  old_balance_dest: number;
  new_balance_dest: number;
}

export interface PredictionResult {
  prediction: 'FRAUD' | 'LEGITIMATE';
  fraud_probability: number;
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
  error_balance_orig: number;
  error_balance_dest: number;
  is_high_value: boolean;
  saved_to_history: boolean;
}

export interface DatasetInfo {
  rows: number;
  columns: string[];
  target_column: string;
  provenance: {
    source: string;
    real_upi_network_data: boolean;
    validation_note?: string;
  };
}

export interface PredictionHistoryRecord {
  id: number;
  amount: number;
  transaction_type: string;
  prediction: 'FRAUD' | 'LEGITIMATE';
  fraud_probability: number;
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
  created_at: string;
}

export interface PredictionHistory {
  predictions: PredictionHistoryRecord[];
  persistence: {
    configured: boolean;
    available: boolean;
    last_error: string | null;
  };
}

export interface ConfusionMatrix { tn: number; fp: number; fn: number; tp: number; }
export interface RocPoint { fpr: number; tpr: number; }
export interface FeatureImportance { feature: string; importance: number; }
export interface ModelComparison {
  Model: string;
  Accuracy: number;
  Precision: number;
  Recall: number;
  F1: number;
  'ROC-AUC': number;
}

export interface PerformanceData {
  metrics: { accuracy: number; precision: number; recall: number; f1: number; roc_auc: number };
  confusion_matrix: ConfusionMatrix;
  roc_curve: RocPoint[];
  feature_importances: FeatureImportance[];
  model_comparison: ModelComparison[];
  best_model_name: string;
  selection_rationale: string;
  evaluation_note: string;
}

export interface CsvAnalysis {
  rows: number;
  columns: string[];
  missing: number;
  fraud_rate?: number;
  fraud_count?: number;
  by_type?: { type: string; total: number; fraud: number; fraud_rate: number }[];
  amount_stats?: {
    legit: { mean: number; median: number };
    fraud: { mean: number; median: number };
  };
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  stats:              ()          => get<Stats>('/api/stats'),
  fraudByType:        ()          => get<FraudByTypeRow[]>('/api/charts/fraud-by-type'),
  fraudByHour:        ()          => get<FraudByHourRow[]>('/api/charts/fraud-by-hour'),
  amountDistribution: ()          => get<AmountDistribution>('/api/charts/amount-distribution'),
  predict:            (body: PredictionInput) => post<PredictionResult>('/api/predict', body),
  performance:        ()          => get<PerformanceData>('/api/performance'),
  datasetInfo:        ()          => get<DatasetInfo>('/api/dataset-info'),
  recentPredictions:  (limit = 10) => get<PredictionHistory>(`/api/predictions?limit=${limit}`),
};

export async function analyseCSV(file: File): Promise<CsvAnalysis> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/analyse-csv`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`CSV analysis failed: ${res.status}`);
  return res.json();
}
