'use client';

import { FormEvent, useState } from 'react';
import AppShell from '@/components/AppShell';
import { api, type PredictionInput, type PredictionResult } from '@/lib/api';

const transactionTypes = ['PAYMENT', 'TRANSFER', 'CASH_OUT', 'CASH_IN', 'DEBIT'];

const initialInput: PredictionInput = {
  amount: 1000,
  transaction_type: 'PAYMENT',
  hour_of_day: 12,
  old_balance_orig: 5000,
  new_balance_orig: 4000,
  old_balance_dest: 1000,
  new_balance_dest: 2000,
};

type NumericField = Exclude<keyof PredictionInput, 'transaction_type'>;

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value);
}

function riskStyles(risk: PredictionResult['risk_level']) {
  if (risk === 'HIGH') return 'bg-red-50 border-red-200 text-red-700';
  if (risk === 'MEDIUM') return 'bg-amber-50 border-amber-200 text-amber-700';
  return 'bg-emerald-50 border-emerald-200 text-emerald-700';
}

export default function TransactionPrediction() {
  const [input, setInput] = useState<PredictionInput>(initialInput);
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateNumber(field: NumericField, value: string) {
    const parsed = Number(value);
    setInput((current) => ({
      ...current,
      [field]: Number.isFinite(parsed) ? parsed : 0,
    }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setIsSubmitting(true);

    try {
      const prediction = await api.predict(input);
      setResult(prediction);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The prediction request could not be completed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-6">
        <section className="bg-primary/5 border border-primary/15 rounded-xl p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">Instant transaction-level estimate</p>
          <h3 className="mt-1 text-xl font-semibold text-text-primary">Score a digital-payment transaction</h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-secondary">
            This sends only the values entered below to the saved model. It does not initiate, observe, or block a real
            UPI payment. Risk bands are model indicators for this educational prototype, not bank decisions.
          </p>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-6 items-start">
          <form onSubmit={submit} className="bg-bg-card border border-border-light rounded-xl p-5 sm:p-6 shadow-card">
            <div className="flex items-start justify-between gap-4 mb-6">
              <div>
                <h4 className="text-base font-semibold text-text-primary">Transaction inputs</h4>
                <p className="mt-1 text-sm text-text-secondary">Use non-negative balances and an hour from 0 to 23.</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setInput(initialInput);
                  setResult(null);
                  setError(null);
                }}
                className="text-sm font-medium text-primary hover:text-primary-dark"
              >
                Reset sample
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="block sm:col-span-2">
                <span className="text-sm font-medium text-text-primary">Transaction amount (₹)</span>
                <input
                  required
                  min="0.01"
                  step="0.01"
                  type="number"
                  value={input.amount}
                  onChange={(event) => updateNumber('amount', event.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-border-light px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-text-primary">Transaction type</span>
                <select
                  value={input.transaction_type}
                  onChange={(event) => setInput((current) => ({ ...current, transaction_type: event.target.value }))}
                  className="mt-1.5 w-full rounded-lg border border-border-light bg-white px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                >
                  {transactionTypes.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>
              </label>

              <label className="block">
                <span className="text-sm font-medium text-text-primary">Hour of day</span>
                <input
                  required
                  min="0"
                  max="23"
                  step="1"
                  type="number"
                  value={input.hour_of_day}
                  onChange={(event) => updateNumber('hour_of_day', event.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-border-light px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-text-primary">Origin balance before</span>
                <input required min="0" step="0.01" type="number" value={input.old_balance_orig} onChange={(event) => updateNumber('old_balance_orig', event.target.value)} className="mt-1.5 w-full rounded-lg border border-border-light px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-text-primary">Origin balance after</span>
                <input required min="0" step="0.01" type="number" value={input.new_balance_orig} onChange={(event) => updateNumber('new_balance_orig', event.target.value)} className="mt-1.5 w-full rounded-lg border border-border-light px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-text-primary">Destination balance before</span>
                <input required min="0" step="0.01" type="number" value={input.old_balance_dest} onChange={(event) => updateNumber('old_balance_dest', event.target.value)} className="mt-1.5 w-full rounded-lg border border-border-light px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-text-primary">Destination balance after</span>
                <input required min="0" step="0.01" type="number" value={input.new_balance_dest} onChange={(event) => updateNumber('new_balance_dest', event.target.value)} className="mt-1.5 w-full rounded-lg border border-border-light px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" />
              </label>
            </div>

            {error && (
              <div role="alert" className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-6 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="material-symbols-outlined text-lg">analytics</span>
              {isSubmitting ? 'Scoring transaction…' : 'Get fraud-risk estimate'}
            </button>
          </form>

          <aside aria-live="polite" className="bg-bg-card border border-border-light rounded-xl p-5 sm:p-6 shadow-card min-h-[260px]">
            {!result && !isSubmitting && (
              <div className="h-full min-h-[210px] flex flex-col items-center justify-center text-center">
                <span className="material-symbols-outlined text-4xl text-primary mb-3">shield_with_heart</span>
                <h4 className="font-semibold text-text-primary">Prediction result</h4>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">Enter transaction details and submit the form to receive a model probability and risk band.</p>
              </div>
            )}

            {isSubmitting && (
              <div className="h-full min-h-[210px] flex flex-col items-center justify-center text-center">
                <span className="material-symbols-outlined text-4xl text-primary animate-pulse mb-3">model_training</span>
                <p className="text-sm font-medium text-text-primary">Running the saved model…</p>
              </div>
            )}

            {result && !isSubmitting && (
              <div className="space-y-5">
                <div className={`rounded-xl border p-4 ${riskStyles(result.risk_level)}`}>
                  <p className="text-xs font-semibold uppercase tracking-wider">Model result</p>
                  <div className="mt-2 flex items-end justify-between gap-3">
                    <span className="text-2xl font-bold">{result.prediction === 'FRAUD' ? 'Potential fraud' : 'Likely legitimate'}</span>
                    <span className="rounded-full bg-white/70 px-2.5 py-1 text-xs font-bold">{result.risk_level} RISK</span>
                  </div>
                  <p className="mt-2 text-sm">Fraud probability: <strong>{(result.fraud_probability * 100).toFixed(2)}%</strong></p>
                </div>

                <dl className="space-y-3 text-sm">
                  <div className="flex items-center justify-between gap-4 border-b border-border-light pb-3">
                    <dt className="text-text-secondary">Entered amount</dt>
                    <dd className="font-semibold text-text-primary">{formatCurrency(input.amount)}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-4 border-b border-border-light pb-3">
                    <dt className="text-text-secondary">Origin balance difference</dt>
                    <dd className="font-semibold text-text-primary">{formatCurrency(result.error_balance_orig)}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-4 border-b border-border-light pb-3">
                    <dt className="text-text-secondary">Destination balance difference</dt>
                    <dd className="font-semibold text-text-primary">{formatCurrency(result.error_balance_dest)}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-text-secondary">High-value feature</dt>
                    <dd className="font-semibold text-text-primary">{result.is_high_value ? 'Yes' : 'No'}</dd>
                  </div>
                </dl>

                <p className="text-xs leading-relaxed text-text-muted">
                  {result.saved_to_history
                    ? 'This estimate was saved to the configured PostgreSQL prediction history.'
                    : 'Prediction history is unavailable until the API is configured with PostgreSQL.'}
                </p>
              </div>
            )}
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
