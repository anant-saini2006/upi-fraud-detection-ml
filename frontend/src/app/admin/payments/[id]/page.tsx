'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api, PaymentIntent, ReviewRecord } from '@/lib/api';

function formatCurrency(amount?: number | null) {
  if (amount == null) return '—';
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
    second: '2-digit',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(d);
}

export default function AdminPaymentDetailPage() {
  const params = useParams();
  const id = params?.id as string;

  const [payment, setPayment] = useState<PaymentIntent | null>(null);
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let isMounted = true;
    api
      .adminGetPayment(id)
      .then((data) => {
        if (isMounted) {
          setPayment(data.payment);
          setReviews(data.reviews || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Payment not found');
          setLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="bg-bg-card rounded-xl border border-border-light p-12 text-center text-text-muted text-sm shadow-card">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        Loading transaction telemetry...
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="bg-bg-card rounded-xl border border-border-light p-8 text-center space-y-4 shadow-card max-w-lg mx-auto">
        <div className="w-12 h-12 rounded-xl bg-red-100 text-red-600 flex items-center justify-center mx-auto text-xl">
          <span className="material-symbols-outlined text-2xl">error</span>
        </div>
        <h3 className="text-base font-semibold text-text-primary">Payment Record Not Found</h3>
        <p className="text-xs text-text-secondary">{error || 'Unable to locate transaction ID.'}</p>
        <Link
          href="/admin"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-dark text-white text-xs font-semibold shadow-sm transition"
        >
          <span className="material-symbols-outlined text-base">arrow_back</span>
          <span>Return to Live Feed</span>
        </Link>
      </div>
    );
  }

  const prob = payment.scoring?.probability ?? 0;
  const probPct = Math.round(prob * 100);
  const band = payment.scoring?.risk_band || 'UNKNOWN';

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Breadcrumb & Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/admin"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-secondary hover:text-primary transition"
        >
          <span className="material-symbols-outlined text-base">arrow_back</span>
          <span>Back to Live Payment Stream</span>
        </Link>
      </div>

      {/* Header Info Banner */}
      <section className="bg-bg-card rounded-xl border border-border-light p-5 sm:p-6 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Payment Intent</span>
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                payment.status === 'succeeded'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : payment.status === 'requires_review'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-red-50 text-red-700 border-red-200'
              }`}
            >
              {payment.status === 'succeeded'
                ? 'Succeeded'
                : payment.status === 'requires_review'
                ? 'Requires Human Review'
                : 'Blocked (Fraud Attempt)'}
            </span>
          </div>
          <h2 className="text-2xl font-bold font-mono text-text-primary mt-1">{payment.id}</h2>
          <p className="text-xs text-text-muted mt-1">Initiated at {formatDateTime(payment.created_at)}</p>
        </div>

        <div className="text-left sm:text-right">
          <span className="text-xs text-text-muted block">Transaction Amount</span>
          <span className="text-3xl font-extrabold text-text-primary font-mono">{formatCurrency(payment.amount)}</span>
        </div>
      </section>

      {/* Grid: Risk & Ledger Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* ML Fraud Scoring Card */}
        <section className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card space-y-4">
          <div className="flex items-center justify-between border-b border-border-light pb-3">
            <h4 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-lg">psychology</span>
              ML Fraud Evaluation
            </h4>
            <span
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold border ${
                band === 'HIGH'
                  ? 'bg-red-50 text-red-700 border-red-200'
                  : band === 'MEDIUM'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-emerald-50 text-emerald-700 border-emerald-200'
              }`}
            >
              Risk Band: {band}
            </span>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-text-muted">Calculated Fraud Probability:</span>
              <span className="font-mono font-bold text-text-primary text-sm">{probPct}% ({prob.toFixed(4)})</span>
            </div>
            <div className="w-full bg-gray-100 h-2.5 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  band === 'HIGH' ? 'bg-danger' : band === 'MEDIUM' ? 'bg-amber-500' : 'bg-success'
                }`}
                style={{ width: `${Math.min(100, Math.max(2, probPct))}%` }}
              />
            </div>
          </div>

          <div>
            <span className="text-xs font-semibold text-text-secondary block mb-2">Key Factor Explanations:</span>
            {(payment.scoring?.reasons || payment.scoring?.top_reasons) && (payment.scoring?.reasons || payment.scoring?.top_reasons)!.length > 0 ? (
              <ul className="space-y-1.5">
                {(payment.scoring?.reasons || payment.scoring?.top_reasons)!.map((reason, idx) => (
                  <li
                    key={idx}
                    className="flex items-center gap-2 text-xs bg-gray-50 border border-border-light rounded-lg px-3 py-2 text-text-secondary"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-text-muted">No anomalous indicators detected. Normal consumer profile.</p>
            )}
          </div>
        </section>

        {/* Ledger & Parties Card */}
        <section className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card space-y-4">
          <div className="flex items-center justify-between border-b border-border-light pb-3">
            <h4 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-lg">account_balance_wallet</span>
              Ledger & VPA Balances
            </h4>
            <span className="text-xs font-mono text-text-muted">Neon DB</span>
          </div>

          <div className="space-y-3 text-xs">
            {/* Sender */}
            <div className="bg-gray-50 rounded-lg p-3 border border-border-light space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="font-semibold text-text-primary">Sender Account</span>
                <span className="font-mono text-text-secondary font-medium">{payment.sender_vpa}</span>
              </div>
              <div className="flex justify-between text-text-muted pt-1 border-t border-border-light">
                <span>Wallet Balance Flow:</span>
                <span className="font-mono text-text-secondary">
                  {payment.origin_balance_before != null && payment.origin_balance_after != null
                    ? `${formatCurrency(payment.origin_balance_before)} → ${formatCurrency(payment.origin_balance_after)}`
                    : 'Unchanged'}
                </span>
              </div>
            </div>

            {/* Receiver */}
            <div className="bg-gray-50 rounded-lg p-3 border border-border-light space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="font-semibold text-text-primary">Merchant Receiver Account</span>
                <span className="font-mono text-text-secondary font-medium">{payment.receiver_vpa}</span>
              </div>
              <div className="flex justify-between text-text-muted pt-1 border-t border-border-light">
                <span>Wallet Balance Flow:</span>
                <span className="font-mono text-text-secondary">
                  {payment.destination_balance_before != null && payment.destination_balance_after != null
                    ? `${formatCurrency(payment.destination_balance_before)} → ${formatCurrency(payment.destination_balance_after)}`
                    : 'Unchanged'}
                </span>
              </div>
            </div>

            {/* Note & Idempotency */}
            <div className="pt-1 space-y-1 text-text-muted">
              {payment.description && (
                <div className="flex justify-between">
                  <span>Order Note:</span>
                  <span className="text-text-primary font-medium">{payment.description}</span>
                </div>
              )}
              {payment.idempotency_key && (
                <div className="flex justify-between">
                  <span>Idempotency Key:</span>
                  <span className="font-mono text-[11px]">{payment.idempotency_key}</span>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>

      {/* Review History Audit Trail */}
      {reviews.length > 0 && (
        <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border-light">
            <h4 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-lg">history</span>
              Human Review Audit Trail
            </h4>
          </div>
          <div className="divide-y divide-border-light">
            {reviews.map((r) => (
              <div key={r.id} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded font-bold uppercase ${
                        r.verdict === 'approved'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {r.verdict}
                    </span>
                    <span className="text-text-muted">Reviewed by {r.reviewer}</span>
                  </div>
                  {r.note && <p className="mt-1 text-text-secondary italic">&ldquo;{r.note}&rdquo;</p>}
                </div>
                <span className="text-text-muted font-mono whitespace-nowrap">{formatDateTime(r.created_at)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
