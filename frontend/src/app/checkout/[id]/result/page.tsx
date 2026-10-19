'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
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

export default function CheckoutResultPage() {
  const params = useParams();
  const id = params?.id as string;

  const [payment, setPayment] = useState<PaymentIntent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let isMounted = true;
    api
      .getPaymentIntent(id)
      .then((data) => {
        if (isMounted) {
          setPayment(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to load transaction result');
          setLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-main flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm text-text-muted">Retrieving settlement outcome...</p>
        </div>
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="min-h-screen bg-bg-main flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-bg-card rounded-2xl border border-red-200 p-8 text-center space-y-4 shadow-card">
          <div className="w-12 h-12 rounded-xl bg-red-100 text-danger flex items-center justify-center mx-auto text-xl">
            <span className="material-symbols-outlined text-2xl">error</span>
          </div>
          <h2 className="text-lg font-bold text-text-primary">Result Not Available</h2>
          <p className="text-xs text-text-secondary">{error || 'Unable to locate transaction state.'}</p>
          <Link
            href="/shop"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-dark text-white text-xs font-semibold shadow-sm transition"
          >
            Back to Shop
          </Link>
        </div>
      </div>
    );
  }

  const prob = payment.scoring?.probability ?? 0;
  const probPct = Math.round(prob * 100);
  const isSuccess = payment.status === 'succeeded';
  const isReview = payment.status === 'requires_review';
  const isBlocked = payment.status === 'blocked';

  return (
    <div className="min-h-screen bg-bg-main flex flex-col justify-between p-4 sm:p-6">
      <header className="max-w-md w-full mx-auto text-center pt-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 bg-white border border-border-light rounded-full text-xs font-semibold text-text-secondary shadow-sm">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Gateway Evaluation Complete</span>
        </div>
      </header>

      <main className="max-w-md w-full mx-auto my-auto">
        <div className="bg-bg-card rounded-2xl border border-border-light p-6 sm:p-8 shadow-card space-y-6">
          {/* Outcome Header */}
          <div className="text-center space-y-2">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center text-3xl mx-auto shadow-sm ${
                isSuccess
                  ? 'bg-emerald-100 text-emerald-600'
                  : isReview
                  ? 'bg-amber-100 text-amber-600'
                  : 'bg-red-100 text-danger'
              }`}
            >
              <span className="material-symbols-outlined text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                {isSuccess ? 'check_circle' : isReview ? 'pending' : 'cancel'}
              </span>
            </div>

            <div>
              <h1 className="text-xl font-bold text-text-primary">
                {isSuccess
                  ? 'Payment Settled Clean'
                  : isReview
                  ? 'Held for Human Review'
                  : 'Transaction Declined'}
              </h1>
              <p className="text-xs text-text-muted mt-0.5">
                {isSuccess
                  ? 'Risk evaluated below the threshold. Ledger balance transferred immediately.'
                  : isReview
                  ? 'Borderline risk detected. Escrow held pending compliance analyst verdict.'
                  : 'High probability of fraud. Payment blocked automatically by policy rule.'}
              </p>
            </div>

            <div className="text-3xl font-extrabold text-text-primary font-mono pt-2">
              {formatCurrency(payment.amount)}
            </div>
          </div>

          {/* Telemetry Breakdown Box */}
          <div className="rounded-xl bg-gray-50 border border-border-light p-4 space-y-3 text-xs">
            <div className="flex justify-between items-center pb-2 border-b border-border-light">
              <span className="text-text-muted font-medium">Model Fraud Probability:</span>
              <span className="font-mono font-bold text-text-primary text-sm">
                {probPct}% ({payment.scoring?.risk_band || 'LOW'})
              </span>
            </div>

            <div className="flex justify-between items-center py-1">
              <span className="text-text-muted">Payer VPA</span>
              <span className="font-mono font-medium text-text-primary">{payment.sender_vpa}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-text-muted">Merchant VPA</span>
              <span className="font-mono font-medium text-text-primary">{payment.receiver_vpa}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-text-muted">Payment Intent ID</span>
              <span className="font-mono text-[10px] text-text-secondary">{payment.id}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-text-muted">Timestamp</span>
              <span className="text-text-secondary">{formatDateTime(payment.created_at)}</span>
            </div>

            {(payment.scoring?.reasons || payment.scoring?.top_reasons) &&
              (payment.scoring?.reasons || payment.scoring?.top_reasons)!.length > 0 && (
                <div className="pt-2 border-t border-border-light">
                  <span className="text-[10px] font-semibold uppercase text-text-muted block mb-1">
                    Risk Factors Flagged:
                  </span>
                  <ul className="space-y-1">
                    {(payment.scoring?.reasons || payment.scoring?.top_reasons)!.map((r, i) => (
                      <li key={i} className="text-[11px] text-text-secondary flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
          </div>

          {/* Action Navigation */}
          <div className="space-y-2 pt-2">
            <Link
              href="/shop"
              className="w-full py-2.5 px-4 rounded-lg bg-primary hover:bg-primary-dark text-white font-medium text-xs shadow-sm transition flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-base">storefront</span>
              <span>Back to Demo Store</span>
            </Link>

            <Link
              href={`/admin/payments/${payment.id}`}
              className="w-full py-2 px-4 rounded-lg border border-border-light bg-white hover:bg-gray-50 text-text-primary font-medium text-xs shadow-sm transition flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-base">admin_panel_settings</span>
              <span>Inspect in Admin Console</span>
            </Link>
          </div>
        </div>
      </main>

      <footer className="py-4 text-center text-xs text-text-muted">
        UPI Fraud Detection Prototype • Gateway Transaction Outcome
      </footer>
    </div>
  );
}
