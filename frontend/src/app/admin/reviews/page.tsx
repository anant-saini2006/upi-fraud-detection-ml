'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, PaymentIntent } from '@/lib/api';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatDateTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    day: 'numeric',
    month: 'short',
  }).format(d);
}

export default function AdminReviewsPage() {
  const [payments, setPayments] = useState<PaymentIntent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [noteInputs, setNoteInputs] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchReviews = async () => {
    try {
      const res = await api.adminListReviews();
      setPayments(res.payments || []);
    } catch {
      // Ignore background errors
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
    const interval = setInterval(fetchReviews, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleVerdict = async (paymentId: string, verdict: 'approved' | 'confirmed_fraud') => {
    setActionInProgress(paymentId);
    setMessage(null);
    try {
      const note = noteInputs[paymentId]?.trim() || undefined;
      await api.adminSubmitReview(paymentId, verdict, note);
      setMessage({
        text: `Payment ${paymentId.substring(0, 14)}... marked as ${
          verdict === 'approved' ? 'APPROVED' : 'CONFIRMED FRAUD'
        }. Ledger updated.`,
        type: 'success',
      });
      // Optimistically remove from list
      setPayments((prev) => prev.filter((p) => p.id !== paymentId));
      window.dispatchEvent(new Event('payments-updated'));
    } catch (err: unknown) {
      setMessage({
        text: err instanceof Error ? err.message : 'Review action failed',
        type: 'error',
      });
    } finally {
      setActionInProgress(null);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  return (
    <div className="space-y-6">
      {/* Hero Banner */}
      <section className="bg-primary/5 border border-primary/15 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">Analyst Review Queue</p>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800">
              {payments.length} Pending
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold text-text-primary">Human-in-the-Loop Decisioning</h3>
          <p className="mt-1 max-w-3xl text-sm text-text-secondary leading-relaxed">
            Transactions held in escrow because their ML fraud probability falls between the Review and Block thresholds.
            Inspect scoring telemetry and make an authoritative determination.
          </p>
        </div>
      </section>

      {/* Action feedback */}
      {message && (
        <div
          className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm font-medium ${
            message.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
          <span className="material-symbols-outlined text-lg">
            {message.type === 'success' ? 'check_circle' : 'error'}
          </span>
          <span>{message.text}</span>
        </div>
      )}

      {/* Main Review List */}
      {loading && payments.length === 0 ? (
        <div className="bg-bg-card rounded-xl border border-border-light p-12 text-center text-text-muted text-sm shadow-card">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          Loading flagged transactions...
        </div>
      ) : payments.length === 0 ? (
        <div className="bg-bg-card rounded-xl border border-border-light p-12 text-center space-y-3 shadow-card">
          <div className="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl mx-auto">
            <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
              task_alt
            </span>
          </div>
          <h4 className="text-base font-semibold text-text-primary">Review Queue is Clear</h4>
          <p className="text-sm text-text-secondary max-w-md mx-auto">
            All flagged transactions have been reviewed. To generate borderline transactions, visit the Demo Store
            or trigger a simulation.
          </p>
          <div className="pt-2">
            <Link
              href="/admin"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-xs font-semibold text-text-primary transition"
            >
              <span className="material-symbols-outlined text-base">arrow_back</span>
              Back to Live Feed
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {payments.map((p) => {
            const prob = p.scoring?.probability ?? 0;
            const probPct = Math.round(prob * 100);
            const reasons = p.scoring?.reasons || p.scoring?.top_reasons || [];
            const isProcessing = actionInProgress === p.id;

            return (
              <article
                key={p.id}
                className="bg-bg-card rounded-xl border border-border-light shadow-card p-5 hover:shadow-card-hover transition-shadow space-y-4"
              >
                {/* Header Row */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border-light pb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center font-bold">
                      <span className="material-symbols-outlined text-xl">rate_review</span>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-text-primary">{formatCurrency(p.amount)}</span>
                        <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-amber-50 text-amber-700 border border-amber-200 font-semibold">
                          Needs Review
                        </span>
                      </div>
                      <p className="text-xs text-text-muted mt-0.5">
                        Initiated {formatDateTime(p.created_at)} · ID: <span className="font-mono">{p.id}</span>
                      </p>
                    </div>
                  </div>

                  <Link
                    href={`/admin/payments/${p.id}`}
                    className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                  >
                    <span>Full Telemetry</span>
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                  </Link>
                </div>

                {/* Flow and Score Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Left: Transaction Flow */}
                  <div className="bg-gray-50 rounded-lg p-3.5 space-y-2 border border-border-light text-xs">
                    <p className="font-semibold text-text-primary uppercase tracking-wider text-[10px]">
                      Ledger Accounts
                    </p>
                    <div className="flex justify-between items-center">
                      <span className="text-text-muted">Sender VPA:</span>
                      <span className="font-mono font-medium text-text-primary">{p.sender_vpa}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-text-muted">Receiver VPA:</span>
                      <span className="font-mono font-medium text-text-primary">{p.receiver_vpa}</span>
                    </div>
                    {p.description && (
                      <div className="flex justify-between items-center pt-1 border-t border-border-light">
                        <span className="text-text-muted">Note:</span>
                        <span className="text-text-secondary">{p.description}</span>
                      </div>
                    )}
                  </div>

                  {/* Right: Fraud Telemetry */}
                  <div className="bg-gray-50 rounded-lg p-3.5 space-y-2 border border-border-light text-xs">
                    <div className="flex justify-between items-center">
                      <span className="font-semibold text-text-primary uppercase tracking-wider text-[10px]">
                        Fraud Risk Estimate
                      </span>
                      <span className="font-mono font-bold text-amber-700">{probPct}% probability</span>
                    </div>
                    {/* Probability bar */}
                    <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-amber-500 h-full rounded-full transition-all"
                        style={{ width: `${Math.min(100, probPct)}%` }}
                      />
                    </div>
                    {reasons.length > 0 && (
                      <div className="pt-1">
                        <span className="text-[10px] text-text-muted block mb-1">Top Risk Indicators:</span>
                        <div className="flex flex-wrap gap-1.5">
                          {reasons.map((r, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 rounded bg-white border border-border-light text-[11px] text-text-secondary"
                            >
                              {r}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Review Actions */}
                <div className="pt-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                  <input
                    type="text"
                    placeholder="Analyst reasoning or audit note (optional)..."
                    value={noteInputs[p.id] || ''}
                    onChange={(e) =>
                      setNoteInputs((prev) => ({ ...prev, [p.id]: e.target.value }))
                    }
                    className="flex-1 px-3 py-2 rounded-lg border border-border-light text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
                  />

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleVerdict(p.id, 'approved')}
                      disabled={isProcessing}
                      className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-sm transition disabled:opacity-50"
                    >
                      <span className="material-symbols-outlined text-base">check</span>
                      <span>Approve & Settle</span>
                    </button>

                    <button
                      onClick={() => handleVerdict(p.id, 'confirmed_fraud')}
                      disabled={isProcessing}
                      className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-sm transition disabled:opacity-50"
                    >
                      <span className="material-symbols-outlined text-base">block</span>
                      <span>Block & Refund</span>
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
