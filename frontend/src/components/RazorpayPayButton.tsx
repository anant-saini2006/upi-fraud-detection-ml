'use client';

import React, { useState, useCallback } from 'react';
import MockRazorpayModal, { MockOrderDetails } from './MockRazorpayModal';

/**
 * Props accepted by the RazorpayPayButton component.
 *
 * @prop productId — must match a key in DEMO_CATALOG on the backend.
 * @prop label     — optional button text override.
 */
interface RazorpayPayButtonProps {
  productId: string;
  label?: string;
}

// The Razorpay checkout script adds `Razorpay` to the global window object.
declare global {
  interface Window {
    Razorpay: any;
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
const RAZORPAY_KEY_ID = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID || '';

/**
 * Load the Razorpay checkout.js script exactly once and resolve when ready.
 */
let _scriptPromise: Promise<void> | null = null;

function ensureRazorpayScript(): Promise<void> {
  if (_scriptPromise) return _scriptPromise;
  _scriptPromise = new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Razorpay) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      // In student test mode or if blocked, resolve anyway to fall back to mock modal!
      resolve();
    };
    document.head.appendChild(script);
  });
  return _scriptPromise;
}

export default function RazorpayPayButton({
  productId,
  label = 'Pay ₹199',
}: RazorpayPayButtonProps) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'failed' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [mockModalOpen, setMockModalOpen] = useState(false);
  const [currentOrder, setCurrentOrder] = useState<MockOrderDetails | null>(null);

  const handleVerify = async (paymentData: {
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) => {
    try {
      const verifyRes = await fetch(`${API_BASE}/payments/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(paymentData),
      });

      if (!verifyRes.ok) {
        const err = await verifyRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Verification failed');
      }

      const result = await verifyRes.json();
      setStatus('success');
      setMessage(
        `Payment verified! Status: ${result.gateway_status}` +
          (result.fraud_status ? ` · Fraud check: ${result.fraud_status}` : '')
      );
    } catch (verifyErr: any) {
      setStatus('error');
      setMessage(`Verification error: ${verifyErr.message}`);
    } finally {
      setMockModalOpen(false);
      setLoading(false);
    }
  };

  const handlePay = useCallback(async () => {
    setLoading(true);
    setStatus('idle');
    setMessage('');

    try {
      // 1. Create order on the backend
      const orderRes = await fetch(`${API_BASE}/payments/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: productId }),
      });

      if (!orderRes.ok) {
        const err = await orderRes.json().catch(() => ({}));
        throw new Error(err.detail || `Order creation failed (${orderRes.status})`);
      }

      const order = await orderRes.json();

      // 2. If backend is in Zero-KYC Mock Mode or no live key configured, open Mock modal
      if (order.is_mock || !RAZORPAY_KEY_ID || order.key_id?.includes('mock')) {
        setCurrentOrder(order);
        setMockModalOpen(true);
        setLoading(false);
        return;
      }

      // 3. Otherwise try loading official Razorpay Standard Checkout
      await ensureRazorpayScript();

      if (!window.Razorpay) {
        // Fallback to Mock modal if script failed to load
        setCurrentOrder(order);
        setMockModalOpen(true);
        setLoading(false);
        return;
      }

      const options = {
        key: RAZORPAY_KEY_ID || order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'UPI Fraud Detection',
        description: order.product_name || 'Demo Purchase',
        order_id: order.order_id,
        handler: handleVerify,
        modal: {
          ondismiss: () => {
            setStatus('failed');
            setMessage('Checkout was cancelled.');
            setLoading(false);
          },
        },
        theme: { color: '#6C63FF' },
      };

      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', (resp: any) => {
        setStatus('failed');
        setMessage(resp?.error?.description || 'Payment failed. Please try again.');
        setLoading(false);
      });
      rzp.open();
    } catch (err: any) {
      setStatus('error');
      setMessage(err.message || 'Something went wrong.');
      setLoading(false);
    }
  }, [productId]);

  return (
    <>
      <div className="inline-flex flex-col items-start gap-2">
        <button
          onClick={handlePay}
          disabled={loading}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-dark transition-colors shadow-md shadow-primary/25 disabled:opacity-60"
        >
          {loading ? (
            <>
              <span className="material-symbols-outlined text-lg animate-spin">progress_activity</span>
              Processing…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-lg">payment</span>
              {label}
            </>
          )}
        </button>

        {status === 'success' && (
          <p className="text-xs text-green-600 font-medium flex items-center gap-1">
            <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
            {message}
          </p>
        )}
        {status === 'failed' && (
          <p className="text-xs text-orange-600 font-medium flex items-center gap-1">
            <span className="material-symbols-outlined text-sm">info</span>
            {message}
          </p>
        )}
        {status === 'error' && (
          <p className="text-xs text-red-600 font-medium flex items-center gap-1">
            <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>error</span>
            {message}
          </p>
        )}
      </div>

      <MockRazorpayModal
        isOpen={mockModalOpen}
        order={currentOrder}
        onClose={() => {
          setMockModalOpen(false);
          setStatus('failed');
          setMessage('Checkout was cancelled.');
        }}
        onSuccess={handleVerify}
        onFailure={(errMsg) => {
          setMockModalOpen(false);
          setStatus('failed');
          setMessage(errMsg);
        }}
      />
    </>
  );
}
