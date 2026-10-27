/**
 * src/lib/api.ts
 * Typed client for the FastAPI backend.
 * All components import from here — single source of truth for API calls.
 */

const API_BASE = (
  typeof window !== 'undefined'
    ? ''
    : (process.env.NEXT_PUBLIC_API_URL?.trim() || 'http://localhost:8000')
).replace(/\/$/, '');
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
    if (res.status === 401 && path.startsWith('/api/admin') && path !== '/api/admin/login') {
      clearAdminToken();
      if (typeof window !== 'undefined' && window.location.pathname.startsWith('/admin') && window.location.pathname !== '/admin/login') {
        window.location.href = '/admin/login';
      }
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
  merchant_category?: string;
}

export interface PredictionResult {
  prediction: 'FRAUD' | 'LEGITIMATE';
  fraud_probability: number;
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
  error_balance_orig: number;
  error_balance_dest: number;
  is_high_value: boolean;
  saved_to_history: boolean;
  input_valid?: boolean;
  validation_errors?: string[];
  policy_verdict?: 'PASS' | 'WARNING' | 'FLAGGED_FOR_REVIEW' | 'REJECTED' | 'OUT_OF_SCOPE';
  policy_action?: 'ALLOW' | 'REVIEW' | 'REJECT';
  reason_codes?: string[];
  reasons?: string[];
  policy_warnings?: string[];
  reconciliation_note?: string;
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
  'PR-AUC'?: number;
  'False Positive Rate'?: number;
  FPR?: number;
}

export interface MetricCiBounds {
  ci_lower_95: number;
  median: number;
  ci_upper_95: number;
}

export interface PerformanceData {
  metrics: {
    accuracy: number;
    precision: number;
    recall: number;
    f1: number;
    roc_auc: number;
    pr_auc?: number;
    false_positive_rate?: number;
  };
  confusion_matrix: ConfusionMatrix;
  roc_curve: RocPoint[];
  feature_importances: FeatureImportance[];
  model_comparison: ModelComparison[];
  best_model_name: string;
  selection_rationale: string;
  evaluation_note: string;
  bootstrap_ci?: Record<string, MetricCiBounds>;
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
  status: 'requires_payment_method' | 'processing' | 'succeeded' | 'requires_review' | 'blocked' | 'cancelled';
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

  cancelPaymentIntent: (id: string) =>
    request<PaymentIntent>(`/v1/payment_intents/${id}/cancel`, {
      method: 'POST',
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

export async function parseAndAnalyseCsvClient(file: File): Promise<CsvAnalysis> {
  if (file.size > 20 * 1024 * 1024) {
    throw new Error('CSV is too large. The limit is 20 MB.');
  }
  if (file.size === 0) {
    throw new Error('The uploaded file is empty.');
  }

  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) {
    throw new Error('CSV file must have a header row and at least one data row.');
  }

  const parseLine = (line: string): string[] => {
    const values: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        if (inQuotes && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === ',' && !inQuotes) {
        values.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    values.push(current.trim());
    return values;
  };

  const headers = parseLine(lines[0]);
  const colIndex: Record<string, number> = {};
  headers.forEach((h, idx) => {
    colIndex[h] = idx;
  });

  let missing = 0;
  let fraudCount = 0;
  const byType: Record<string, { total: number; fraud: number }> = {};
  const legitAmounts: number[] = [];
  const fraudAmounts: number[] = [];

  const hasIsFraud = 'isFraud' in colIndex;
  const hasType = 'type' in colIndex;
  const hasAmount = 'amount' in colIndex;
  const isFraudIdx = colIndex['isFraud'];
  const typeIdx = colIndex['type'];
  const amountIdx = colIndex['amount'];

  const rowCount = lines.length - 1;

  for (let i = 1; i < lines.length; i++) {
    const parts = parseLine(lines[i]);
    for (let c = 0; c < headers.length; c++) {
      const val = parts[c] ?? '';
      if (val === '' || val === 'NaN' || val === 'null' || val === 'None') {
        missing++;
      }
    }

    let isFraudVal = 0;
    if (hasIsFraud) {
      const parsedFraud = Number(parts[isFraudIdx]);
      if (!Number.isNaN(parsedFraud)) {
        isFraudVal = parsedFraud === 1 ? 1 : 0;
        if (isFraudVal === 1) fraudCount++;
      }
    }

    if (hasType) {
      const t = parts[typeIdx]?.trim() || 'UNKNOWN';
      if (!byType[t]) byType[t] = { total: 0, fraud: 0 };
      byType[t].total++;
      if (isFraudVal === 1) byType[t].fraud++;
    }

    if (hasAmount) {
      const amt = Number(parts[amountIdx]);
      if (!Number.isNaN(amt)) {
        if (isFraudVal === 1) fraudAmounts.push(amt);
        else legitAmounts.push(amt);
      }
    }
  }

  function median(arr: number[]): number {
    if (arr.length === 0) return 0;
    arr.sort((a, b) => a - b);
    const mid = Math.floor(arr.length / 2);
    return arr.length % 2 !== 0 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
  }

  function mean(arr: number[]): number {
    if (arr.length === 0) return 0;
    return arr.reduce((acc, v) => acc + v, 0) / arr.length;
  }

  const byTypeArr = Object.keys(byType).map((t) => ({
    type: t,
    total: byType[t].total,
    fraud: byType[t].fraud,
    fraud_rate: Number(((byType[t].fraud / byType[t].total) * 100).toFixed(4)),
  }));

  return {
    rows: rowCount,
    columns: headers,
    missing,
    fraud_rate: hasIsFraud ? Number(((fraudCount / rowCount) * 100).toFixed(4)) : undefined,
    fraud_count: hasIsFraud ? fraudCount : undefined,
    by_type: hasType && byTypeArr.length > 0 ? byTypeArr : undefined,
    amount_stats: hasAmount
      ? {
          legit: { mean: Number(mean(legitAmounts).toFixed(2)), median: Number(median(legitAmounts).toFixed(2)) },
          fraud: { mean: Number(mean(fraudAmounts).toFixed(2)), median: Number(median(fraudAmounts).toFixed(2)) },
        }
      : undefined,
  };
}

export async function analyseCSV(file: File): Promise<CsvAnalysis> {
  // Vercel serverless has a hard request body limit of 4.5 MB.
  // Files over 3.5 MB are parsed directly in the browser to prevent FUNCTION_PAYLOAD_TOO_LARGE.
  if (file.size > 3.5 * 1024 * 1024) {
    return parseAndAnalyseCsvClient(file);
  }

  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/analyse-csv`, { method: 'POST', body: form });
    if (!res.ok) {
      return parseAndAnalyseCsvClient(file);
    }
    return res.json();
  } catch {
    // If Vercel edge drops connection or fails CORS on payload limits, fallback seamlessly to client parsing
    return parseAndAnalyseCsvClient(file);
  }
}
