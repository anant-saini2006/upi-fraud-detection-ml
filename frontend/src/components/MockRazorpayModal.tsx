'use client';

import React, { useState, useEffect } from 'react';

export interface MockOrderDetails {
  order_id: string;
  amount: number; // in paise
  currency: string;
  product_name: string;
  key_id: string;
}

interface MockRazorpayModalProps {
  isOpen: boolean;
  order: MockOrderDetails | null;
  onClose: () => void;
  onSuccess: (paymentData: {
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) => void;
  onFailure: (errorMessage: string) => void;
}

/**
 * Computes an authentic HMAC-SHA256 signature using the browser's Web Crypto API
 * so the backend verification endpoint performs a real cryptographic check.
 */
async function computeMockHmacSha256(orderId: string, paymentId: string): Promise<string> {
  const secret = 'mock_secret_key_demo_only';
  try {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw',
      enc.encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );
    const signature = await crypto.subtle.sign(
      'HMAC',
      key,
      enc.encode(`${orderId}|${paymentId}`)
    );
    return Array.from(new Uint8Array(signature))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    return 'mock_signature_bypass';
  }
}

export default function MockRazorpayModal({
  isOpen,
  order,
  onClose,
  onSuccess,
  onFailure,
}: MockRazorpayModalProps) {
  const [activeTab, setActiveTab] = useState<'upi' | 'card' | 'netbanking'>('upi');
  const [vpa, setVpa] = useState('student@okaxis');
  const [cardNumber, setCardNumber] = useState('4111 2222 3333 4444');
  const [cardExpiry, setCardExpiry] = useState('12/28');
  const [cardCvv, setCardCvv] = useState('123');
  const [selectedBank, setSelectedBank] = useState('HDFC');
  const [processingStep, setProcessingStep] = useState<'idle' | 'authorizing' | 'success'>('idle');

  useEffect(() => {
    if (isOpen) {
      setProcessingStep('idle');
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen || !order) return null;

  const displayAmount = (order.amount / 100).toFixed(2);

  const handleSimulateSuccess = async () => {
    setProcessingStep('authorizing');

    setTimeout(async () => {
      const mockPaymentId = `pay_mock_${Math.random().toString(36).substring(2, 10)}${Date.now().toString().slice(-4)}`;
      const signature = await computeMockHmacSha256(order.order_id, mockPaymentId);

      setProcessingStep('success');

      setTimeout(() => {
        onSuccess({
          razorpay_order_id: order.order_id,
          razorpay_payment_id: mockPaymentId,
          razorpay_signature: signature,
        });
      }, 700);
    }, 1100);
  };

  const handleSimulateDecline = () => {
    onFailure('Payment declined by issuing bank (Simulated Sandbox Rejection).');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/65 backdrop-blur-sm animate-fadeIn">
      <div
        className="w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200 animate-scaleUp text-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Razorpay Brand Header */}
        <div className="bg-[#0c2340] text-white px-6 py-4 flex items-center justify-between relative">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-black text-white text-lg tracking-tighter shadow-md">
              R
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-tight">Razorpay Checkout</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-400 text-slate-900 uppercase tracking-wide">
                  Test Sandbox
                </span>
              </div>
              <p className="text-xs text-slate-300 font-medium">{order.product_name}</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-semibold">Amount</span>
              <span className="text-lg font-mono font-bold text-white">₹{displayAmount}</span>
            </div>
            <button
              onClick={onClose}
              disabled={processingStep !== 'idle'}
              className="w-7 h-7 rounded-full bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white flex items-center justify-center transition disabled:opacity-40"
              title="Close modal"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Processing State Overlay */}
        {processingStep !== 'idle' ? (
          <div className="py-16 px-6 text-center space-y-4">
            {processingStep === 'authorizing' ? (
              <>
                <div className="w-14 h-14 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
                <div className="space-y-1">
                  <h4 className="text-base font-semibold text-slate-900">Contacting Bank UPI Server…</h4>
                  <p className="text-xs text-slate-500 font-mono">
                    Order ID: {order.order_id} · Generating HMAC-SHA256 signature
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto text-2xl animate-bounce">
                  ✓
                </div>
                <div className="space-y-1">
                  <h4 className="text-base font-bold text-emerald-700">Payment Captured!</h4>
                  <p className="text-xs text-slate-500">Transmitting verification payload to FastAPI backend…</p>
                </div>
              </>
            )}
          </div>
        ) : (
          <div>
            {/* Payment Method Selector Tabs */}
            <div className="grid grid-cols-3 border-b border-slate-200 bg-slate-50 text-xs font-semibold">
              <button
                onClick={() => setActiveTab('upi')}
                className={`py-3 px-4 flex items-center justify-center gap-1.5 transition ${
                  activeTab === 'upi'
                    ? 'border-b-2 border-blue-600 text-blue-600 bg-white'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span className="text-sm">⚡</span> UPI / QR
              </button>
              <button
                onClick={() => setActiveTab('card')}
                className={`py-3 px-4 flex items-center justify-center gap-1.5 transition ${
                  activeTab === 'card'
                    ? 'border-b-2 border-blue-600 text-blue-600 bg-white'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span className="text-sm">💳</span> Cards (Test)
              </button>
              <button
                onClick={() => setActiveTab('netbanking')}
                className={`py-3 px-4 flex items-center justify-center gap-1.5 transition ${
                  activeTab === 'netbanking'
                    ? 'border-b-2 border-blue-600 text-blue-600 bg-white'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span className="text-sm">🏛️</span> Netbanking
              </button>
            </div>

            {/* Tab 1: UPI View */}
            {activeTab === 'upi' && (
              <div className="p-6 space-y-5">
                <div className="flex flex-col sm:flex-row items-center gap-5 p-4 rounded-xl bg-slate-50 border border-slate-200">
                  {/* High Quality Styled QR Code */}
                  <div className="relative shrink-0 p-2.5 bg-white rounded-lg border border-slate-300 shadow-sm">
                    <svg
                      className="w-28 h-28"
                      viewBox="0 0 100 100"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <rect width="100" height="100" fill="white" />
                      {/* Top-left corner box */}
                      <rect x="10" y="10" width="24" height="24" fill="#0f172a" rx="2" />
                      <rect x="14" y="14" width="16" height="16" fill="white" />
                      <rect x="18" y="18" width="8" height="8" fill="#0f172a" />

                      {/* Top-right corner box */}
                      <rect x="66" y="10" width="24" height="24" fill="#0f172a" rx="2" />
                      <rect x="70" y="14" width="16" height="16" fill="white" />
                      <rect x="74" y="18" width="8" height="8" fill="#0f172a" />

                      {/* Bottom-left corner box */}
                      <rect x="10" y="66" width="24" height="24" fill="#0f172a" rx="2" />
                      <rect x="14" y="70" width="16" height="16" fill="white" />
                      <rect x="18" y="74" width="8" height="8" fill="#0f172a" />

                      {/* Data Pattern Modules */}
                      <rect x="42" y="12" width="6" height="6" fill="#0f172a" />
                      <rect x="52" y="12" width="6" height="6" fill="#0f172a" />
                      <rect x="42" y="24" width="16" height="6" fill="#0f172a" />
                      <rect x="12" y="42" width="16" height="6" fill="#0f172a" />
                      <rect x="34" y="42" width="6" height="16" fill="#0f172a" />
                      <rect x="46" y="38" width="12" height="12" fill="#2563eb" rx="2" />
                      <rect x="66" y="42" width="20" height="6" fill="#0f172a" />
                      <rect x="42" y="58" width="6" height="12" fill="#0f172a" />
                      <rect x="56" y="58" width="12" height="6" fill="#0f172a" />
                      <rect x="42" y="78" width="18" height="6" fill="#0f172a" />
                      <rect x="68" y="70" width="8" height="16" fill="#0f172a" />
                      <rect x="82" y="78" width="8" height="8" fill="#0f172a" />
                    </svg>
                    <div className="text-[9px] text-center font-bold text-slate-500 uppercase tracking-wider mt-1">
                      UPI Test QR
                    </div>
                  </div>

                  <div className="space-y-1.5 text-center sm:text-left">
                    <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700">
                      Scan with any UPI App
                    </div>
                    <h5 className="text-xs font-semibold text-slate-800">
                      Google Pay · PhonePe · Paytm · BHIM
                    </h5>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      Simulated QR linked to merchant account for order{' '}
                      <span className="font-mono text-slate-700 font-semibold">{order.order_id.slice(0, 16)}</span>.
                    </p>
                  </div>
                </div>

                {/* VPA Input */}
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-700">
                    Or pay with UPI ID / VPA
                  </label>
                  <input
                    type="text"
                    value={vpa}
                    onChange={(e) => setVpa(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono font-medium rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition text-slate-800 bg-white"
                    placeholder="username@bank"
                  />
                </div>

                {/* Simulation Action Buttons */}
                <div className="pt-2 space-y-2">
                  <button
                    onClick={handleSimulateSuccess}
                    className="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-md transition flex items-center justify-center gap-2"
                  >
                    <span>✓</span>
                    <span>Simulate Successful UPI Payment (₹{displayAmount})</span>
                  </button>
                  <button
                    onClick={handleSimulateDecline}
                    className="w-full py-1.5 px-3 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-600 font-medium text-xs transition"
                  >
                    Simulate Bank Decline / Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Tab 2: Test Card View */}
            {activeTab === 'card' && (
              <div className="p-6 space-y-4">
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-[11px] text-blue-800 flex items-center gap-2">
                  <span>ℹ️</span>
                  <span>Pre-filled with Razorpay test card. No real card charge will be made.</span>
                </div>

                <div className="space-y-3 text-xs">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Card Number</label>
                    <input
                      type="text"
                      value={cardNumber}
                      onChange={(e) => setCardNumber(e.target.value)}
                      className="w-full px-3 py-2 font-mono rounded-lg border border-slate-300 text-slate-800"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Expiry</label>
                      <input
                        type="text"
                        value={cardExpiry}
                        onChange={(e) => setCardExpiry(e.target.value)}
                        className="w-full px-3 py-2 font-mono rounded-lg border border-slate-300 text-slate-800"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">CVV</label>
                      <input
                        type="password"
                        value={cardCvv}
                        onChange={(e) => setCardCvv(e.target.value)}
                        className="w-full px-3 py-2 font-mono rounded-lg border border-slate-300 text-slate-800"
                      />
                    </div>
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleSimulateSuccess}
                    className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-md transition flex items-center justify-center gap-2"
                  >
                    <span>Pay ₹{displayAmount} with Test Card</span>
                  </button>
                </div>
              </div>
            )}

            {/* Tab 3: Netbanking View */}
            {activeTab === 'netbanking' && (
              <div className="p-6 space-y-4">
                <p className="text-xs text-slate-600 font-medium">Select a bank to simulate Netbanking:</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {['HDFC', 'SBI', 'ICICI', 'Axis', 'Kotak', 'PNB'].map((bank) => (
                    <button
                      key={bank}
                      onClick={() => setSelectedBank(bank)}
                      className={`p-2.5 rounded-lg border text-left font-semibold transition ${
                        selectedBank === bank
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-slate-200 hover:bg-slate-50 text-slate-700'
                      }`}
                    >
                      🏦 {bank} Bank
                    </button>
                  ))}
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleSimulateSuccess}
                    className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-md transition flex items-center justify-center gap-2"
                  >
                    <span>Proceed with {selectedBank} (₹{displayAmount})</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-500">
          <div className="flex items-center gap-1.5 font-medium">
            <span className="text-emerald-600">🔒</span> End-to-end 256-bit encrypted test
          </div>
          <span className="font-mono text-[10px]">Zero-KYC Mock Gateway</span>
        </div>
      </div>
    </div>
  );
}
