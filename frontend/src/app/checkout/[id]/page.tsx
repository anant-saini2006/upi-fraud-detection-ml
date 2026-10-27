'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api, PaymentIntent } from '@/lib/api';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function CheckoutPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const id = params?.id as string;
  const hourParam = searchParams?.get('hour');
  const simulatedHour = hourParam !== null ? parseInt(hourParam, 10) : undefined;

  const [payment, setPayment] = useState<PaymentIntent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [confirming, setConfirming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [upiPin, setUpiPin] = useState<string>('••••');

  useEffect(() => {
    if (!id) return;
    let isMounted = true;
    api
      .getPaymentIntent(id)
      .then((data) => {
        if (isMounted) {
          setPayment(data);
          setLoading(false);
          // If already settled, redirect directly to result
          if (data.status !== 'requires_payment_method') {
            router.replace(`/checkout/${id}/result`);
          }
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to load checkout details');
          setLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [id, router]);

  const [cancelling, setCancelling] = useState<boolean>(false);

  const handleCancel = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (cancelling) return;
    setCancelling(true);
    try {
      await api.cancelPaymentIntent(id);
    } catch {
      // Gracefully ignore cancellation network failure and proceed back to store
    } finally {
      router.push('/shop');
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      await api.confirmPaymentIntent(id, simulatedHour);
      router.push(`/checkout/${id}/result`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Transaction confirmation failed');
      setConfirming(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-main flex flex-col justify-between">
      {/* Test Mode Banner */}
      <div className="bg-amber-500 text-neutral-900 px-4 py-2 text-center text-xs font-semibold tracking-wide shadow-sm flex items-center justify-center gap-2">
        <span className="w-2 h-2 rounded-full bg-neutral-900 animate-pulse" />
        <span>TEST MODE CHECKOUT — SIMULATED VIRTUAL PAYMENT ADDRESSES</span>
      </div>

      {/* Top Header */}
      <header className="border-b border-border-light bg-bg-card">
        <div className="max-w-2xl mx-auto px-4 h-16 flex items-center justify-between">
          <button
            onClick={handleCancel}
            disabled={cancelling || confirming}
            className="text-xs text-text-secondary hover:text-text-primary transition flex items-center gap-1.5 font-medium disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-base">arrow_back</span>
            <span>{cancelling ? 'Cancelling...' : 'Cancel and return to store'}</span>
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-white text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                shield
              </span>
            </div>
            <span className="text-xs font-bold text-text-primary">UPI Gateway Checkout</span>
          </div>
        </div>
      </header>

      {/* Main Checkout Container */}
      <main className="max-w-md w-full mx-auto px-4 py-8">
        {loading ? (
          <div className="bg-bg-card rounded-2xl border border-border-light p-12 text-center text-text-muted text-sm shadow-card">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            Loading checkout session...
          </div>
        ) : error && !payment ? (
          <div className="bg-bg-card rounded-2xl border border-red-200 p-8 text-center space-y-4 shadow-card">
            <div className="w-12 h-12 rounded-xl bg-red-100 text-danger flex items-center justify-center mx-auto text-xl">
              <span className="material-symbols-outlined text-2xl">error</span>
            </div>
            <h3 className="text-base font-semibold text-text-primary">Checkout Session Error</h3>
            <p className="text-xs text-text-secondary">{error}</p>
            <Link
              href="/shop"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-xs font-semibold text-text-primary transition"
            >
              Return to Demo Store
            </Link>
          </div>
        ) : payment ? (
          <div className="bg-bg-card rounded-2xl border border-border-light p-6 sm:p-8 shadow-card space-y-6">
            {/* Amount & Description */}
            <div className="text-center space-y-1">
              <span className="text-xs font-medium text-text-muted uppercase tracking-wider">Amount to Pay</span>
              <div className="text-3xl sm:text-4xl font-extrabold text-text-primary tracking-tight font-mono">
                {formatCurrency(payment.amount)}
              </div>
              <p className="text-xs text-text-secondary font-medium">{payment.description || 'Order Payment'}</p>
            </div>

            {/* Payment Details */}
            <div className="rounded-xl bg-gray-50 border border-border-light p-4 space-y-3 text-xs">
              <div className="flex justify-between items-center py-1 border-b border-border-light">
                <span className="text-text-muted">Payer VPA</span>
                <span className="font-mono font-medium text-text-primary">{payment.sender_vpa}</span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-border-light">
                <span className="text-text-muted">Merchant VPA</span>
                <span className="font-mono font-medium text-text-primary">{payment.receiver_vpa}</span>
              </div>
              {simulatedHour !== undefined && (
                <div className="flex justify-between items-center py-1 border-b border-border-light">
                  <span className="text-text-muted">Simulated Hour</span>
                  <span className="font-mono font-bold text-primary">
                    {String(simulatedHour).padStart(2, '0')}:00 {simulatedHour < 6 || simulatedHour >= 22 ? '🌙 Night' : '☀️ Day'}
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center py-1">
                <span className="text-text-muted">Payment Intent ID</span>
                <span className="font-mono text-[10px] text-text-secondary">{payment.id.substring(0, 16)}...</span>
              </div>
            </div>

            {/* Simulated UPI PIN Input */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <label className="font-semibold text-text-primary">Simulated UPI PIN</label>
                <span className="text-text-muted">Auto-filled (Test)</span>
              </div>
              <input
                type="password"
                value={upiPin}
                onChange={(e) => setUpiPin(e.target.value)}
                maxLength={6}
                className="w-full text-center text-lg tracking-[0.5em] py-2 px-3 rounded-lg border border-border-light bg-gray-50 text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition font-mono font-bold"
              />
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs font-medium text-danger flex items-center gap-2">
                <span className="material-symbols-outlined text-base">error</span>
                <span>{error}</span>
              </div>
            )}

            {/* Confirm CTA */}
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="w-full py-3 px-4 rounded-lg bg-primary hover:bg-primary-dark text-white font-semibold text-sm shadow-sm transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {confirming ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Scoring Risk & Authorizing...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-lg">check_circle</span>
                  <span>Authorize & Pay {formatCurrency(payment.amount)}</span>
                </>
              )}
            </button>

            <p className="text-[11px] text-text-muted text-center leading-relaxed">
              Upon confirmation, this transaction is evaluated against the trained PaySim ML model and active risk
              policy thresholds.
            </p>
          </div>
        ) : null}
      </main>

      <footer className="py-4 text-center text-xs text-text-muted">
        UPI Fraud Detection Prototype • Secure Hosted Checkout
      </footer>
    </div>
  );
}
