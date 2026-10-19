/**
 * src/lib/api.ts
 * Typed client for the FastAPI backend.
 * All components import from here — single source of truth for API calls.
 */

const API_BASE = (process.env.NEXT_PUBLIC_API_URL?.trim() || (typeof window !== 'undefined' ? '' : 'http://localhost:8000')).replace(/\/$/, '');
const GATEWAY_TEST_KEY = process.env.NEXT_PUBLIC_GATEWAY_KEY?.trim() || 'sk_test_demo_key_001';

// Admin session storage helpers
export function getAdminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_session_token');
}

export function setAdminToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('admin_session_token', token);
  }
}

export function clearAdminToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('admin_session_token');
  }
}

async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
  } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: 'no-store',
  });

  if (!res.ok) {
    let errorDetail = `API error ${res.status}`;
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      const text = await res.text();
      if (text) errorDetail = text;
    }
    throw new Error(errorDetail);
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

// ── Gateway & Admin Types ─────────────────────────────────────────────────────

export interface ScoringResponse {
  probability: number;
  label: 'FRAUD' | 'LEGITIMATE';
  risk_band: 'LOW' | 'MEDIUM' | 'HIGH';
  reasons: string[];
  top_reasons?: string[];
}

export interface PaymentIntent {
  id: string;
  amount: number;
  currency: string;
  sender_vpa: string;
  receiver_vpa: string;
  description: string | null;
  status: 'requires_payment_method' | 'processing' | 'succeeded' | 'requires_review' | 'blocked';
  scoring: ScoringResponse | null;
  decline_reason: string | null;
  created_at: string;
  confirmed_at: string | null;
  simulated_hour: number | null;
  scenario_tag: string | null;
  idempotency_key?: string | null;
  origin_balance_before?: number | null;
  origin_balance_after?: number | null;
  destination_balance_before?: number | null;
  destination_balance_after?: number | null;
}

export interface ThresholdSettings {
  block_threshold: number;
  review_threshold: number;
}

export interface AccountInfo {
  vpa: string;
  display_name: string;
  wallet_balance: number;
  total_sent: number;
  total_received: number;
  tx_count: number;
}

export interface ReviewRecord {
  id: number;
  payment_id: string;
  reviewer: string;
  verdict: 'approved' | 'confirmed_fraud';
  note: string | null;
  created_at: string;
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  // Existing Model & Dashboard Endpoints
  stats:              () => request<Stats>('/api/stats'),
  fraudByType:        () => request<FraudByTypeRow[]>('/api/charts/fraud-by-type'),
  fraudByHour:        () => request<FraudByHourRow[]>('/api/charts/fraud-by-hour'),
  amountDistribution: () => request<AmountDistribution>('/api/charts/amount-distribution'),
  predict:            (body: PredictionInput) => request<PredictionResult>('/api/predict', { method: 'POST', body }),
  performance:        () => request<PerformanceData>('/api/performance'),
  datasetInfo:        () => request<DatasetInfo>('/api/dataset-info'),
  recentPredictions:  (limit = 10) => request<PredictionHistory>(`/api/predictions?limit=${limit}`),
  warmup:             () => request<{ status: string }>('/api/warmup'),

  // Gateway API (Test Mode)
  createPaymentIntent: (
    data: { amount: number; sender_vpa: string; receiver_vpa: string; description?: string; currency?: string; scenario_tag?: string },
    idempotencyKey?: string
  ) =>
    request<PaymentIntent>('/v1/payment_intents', {
      method: 'POST',
      body: data,
      headers: {
        Authorization: `Bearer ${GATEWAY_TEST_KEY}`,
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      },
    }),

  confirmPaymentIntent: (id: string, simulated_hour?: number) =>
    request<PaymentIntent>(`/v1/payment_intents/${id}/confirm`, {
      method: 'POST',
      body: { simulated_hour },
      headers: {
        Authorization: `Bearer ${GATEWAY_TEST_KEY}`,
      },
    }),

  getPaymentIntent: (id: string) =>
    request<PaymentIntent>(`/v1/payment_intents/${id}`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${GATEWAY_TEST_KEY}`,
      },
    }),

  // Admin API
  adminLogin: (body: { username: string; password: string }) =>
    request<{ token: string; username: string }>('/api/admin/login', {
      method: 'POST',
      body,
    }),

  adminListPayments: (limit = 50, status?: string) => {
    const token = getAdminToken();
    const query = new URLSearchParams({ limit: String(limit) });
    if (status) query.set('status', status);
    return request<{ payments: PaymentIntent[]; total: number }>(`/api/admin/payments?${query.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminGetPayment: (id: string) => {
    const token = getAdminToken();
    return request<{ payment: PaymentIntent; reviews: ReviewRecord[] }>(`/api/admin/payments/${id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminReviewCount: () => {
    const token = getAdminToken();
    return request<{ count: number }>('/api/admin/review-count', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminListReviews: () => {
    const token = getAdminToken();
    return request<{ payments: PaymentIntent[]; total: number }>('/api/admin/reviews', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminSubmitReview: (paymentId: string, verdict: 'approved' | 'confirmed_fraud', note?: string) => {
    const token = getAdminToken();
    return request<ReviewRecord>(`/api/admin/reviews/${paymentId}`, {
      method: 'POST',
      body: { verdict, note },
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminGetSettings: () => {
    const token = getAdminToken();
    return request<ThresholdSettings>('/api/admin/settings', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminUpdateSettings: (settings: ThresholdSettings) => {
    const token = getAdminToken();
    return request<ThresholdSettings>('/api/admin/settings', {
      method: 'PUT',
      body: settings,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminListAccounts: () => {
    const token = getAdminToken();
    return request<{ accounts: AccountInfo[] }>('/api/admin/accounts', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminSimulate: (count = 50) => {
    const token = getAdminToken();
    return request<{ simulated: number; results: Record<string, number> }>('/api/admin/simulate', {
      method: 'POST',
      body: { count },
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  adminReset: () => {
    const token = getAdminToken();
    return request<{ status: string; message: string }>('/api/admin/reset', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },
};

export async function analyseCSV(file: File): Promise<CsvAnalysis> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/analyse-csv`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`CSV analysis failed: ${res.status}`);
  return res.json();
}
