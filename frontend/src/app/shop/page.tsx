'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppShell from '@/components/AppShell';
import { api } from '@/lib/api';

interface Product {
  id: string;
  name: string;
  price: number;
  description: string;
  icon: string;
  category: string;
}

const PRODUCTS: Product[] = [
  {
    id: 'prod_1',
    name: 'Wireless Noise-Canceling Earbuds',
    price: 499,
    description: 'High-fidelity audio with 36hr battery life and instant Bluetooth pairing.',
    icon: 'headphones',
    category: 'Audio',
  },
  {
    id: 'prod_2',
    name: 'Aero Ultra Smart Watch',
    price: 2999,
    description: 'Continuous biometric tracking, sleep telemetry, and AMOLED display.',
    icon: 'watch',
    category: 'Wearables',
  },
  {
    id: 'prod_3',
    name: 'Ergonomic Aluminium Laptop Stand',
    price: 1499,
    description: 'Precision CNC-machined aerospace alloy with dynamic elevation angles.',
    icon: 'laptop_mac',
    category: 'Accessories',
  },
];

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function ShopPage() {
  const router = useRouter();
  const [simulatedHour, setSimulatedHour] = useState<number>(14);
  const [isSubmitting, setIsSubmitting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rapidStatus, setRapidStatus] = useState<string | null>(null);

  // Custom form state
  const [customAmount, setCustomAmount] = useState<number>(1200);
  const [customSender, setCustomSender] = useState<string>('alice@testpay');
  const [customReceiver, setCustomReceiver] = useState<string>('bob@testpay');
  const [customDesc, setCustomDesc] = useState<string>('Custom payment test');

  const handleBuy = async (
    amount: number,
    description: string,
    senderVpa = 'alice@testpay',
    receiverVpa = 'bob@testpay',
    hourOverride?: number,
    scenarioTag?: string
  ) => {
    const targetHour = hourOverride !== undefined ? hourOverride : simulatedHour;
    setIsSubmitting(description);
    setError(null);
    try {
      const intent = await api.createPaymentIntent({
        amount,
        sender_vpa: senderVpa,
        receiver_vpa: receiverVpa,
        description,
        currency: 'INR',
        scenario_tag: scenarioTag,
      });
      router.push(`/checkout/${intent.id}?hour=${targetHour}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to initialize payment');
      setIsSubmitting(null);
    }
  };

  const handleRapidRepeats = async () => {
    setIsSubmitting('rapid');
    setRapidStatus('Firing 5 rapid payments...');
    setError(null);
    try {
      for (let i = 1; i <= 5; i++) {
        setRapidStatus(`Submitting payment ${i} of 5 (₹9,999)...`);
        const pi = await api.createPaymentIntent(
          {
            amount: 9999,
            sender_vpa: 'eve@testpay',
            receiver_vpa: 'mallory@testpay',
            description: `Rapid Repeat Transaction #${i}`,
            scenario_tag: 'rapid_repeat',
          },
          `rapid_${Date.now()}_${i}`
        );
        await api.confirmPaymentIntent(pi.id, 2);
      }
      setRapidStatus('5 rapid payments completed! Redirecting to Admin live feed...');
      setTimeout(() => {
        router.push('/admin');
      }, 1200);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Rapid test failed');
      setIsSubmitting(null);
      setRapidStatus(null);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-6xl mx-auto">
        {/* Prototype Banner */}
        <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-xs sm:text-sm text-amber-900">
          <span className="material-symbols-outlined text-amber-700 text-lg">science</span>
          <span>
            <strong>Simulated Test Environment:</strong> All transactions use fake test VPAs (@testpay) and synthetic
            balances. No real money or banks are involved.
          </span>
        </div>

        {/* Hero Banner */}
        <section className="bg-primary/5 border border-primary/15 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">Interactive Evaluation Sandbox</p>
            <h3 className="mt-1 text-xl font-semibold text-text-primary">Demo Store & Fraud Simulator</h3>
            <p className="mt-1 max-w-3xl text-sm text-text-secondary leading-relaxed">
              Experience the hosted checkout flow end-to-end. Trigger predefined fraud scenarios or change the simulated clock
              to see how the ML model scores risk in real time.
            </p>
          </div>
          <Link
            href="/admin"
            className="shrink-0 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-bg-card border border-border-light text-text-primary text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors shadow-card"
          >
            <span className="material-symbols-outlined text-lg">admin_panel_settings</span>
            Admin Live Feed
          </Link>
        </section>

        {/* Scenario Controls Box */}
        <section className="bg-bg-card rounded-xl border border-border-light p-5 sm:p-6 shadow-card space-y-6">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div>
              <h4 className="text-base font-semibold text-text-primary">One-Click Demonstration Scenarios</h4>
              <p className="text-xs text-text-muted mt-0.5">
                Quickly trigger characteristic transaction patterns to test gateway decisions.
              </p>
            </div>

            {/* Simulated Hour Slider */}
            <div className="bg-gray-50 border border-border-light rounded-xl p-3 sm:min-w-[300px]">
              <div className="flex justify-between items-center mb-1 text-xs">
                <span className="text-text-muted font-medium">Clock Override:</span>
                <span className="font-mono text-primary font-bold">
                  {String(simulatedHour).padStart(2, '0')}:00 {simulatedHour < 6 || simulatedHour >= 22 ? '🌙 Night' : '☀️ Day'}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="23"
                value={simulatedHour}
                onChange={(e) => setSimulatedHour(parseInt(e.target.value, 10))}
                className="w-full accent-primary cursor-pointer h-1.5"
              />
              <div className="flex justify-between text-[10px] text-text-muted font-mono mt-1">
                <span>00:00 (Risk ↑)</span>
                <span>12:00 (Normal)</span>
                <span>23:00 (Risk ↑)</span>
              </div>
            </div>
          </div>

          {/* Preset Buttons Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Scenario A */}
            <button
              onClick={() => {
                setSimulatedHour(14);
                handleBuy(499, 'Legitimate Day Purchase (Alice)', 'alice@testpay', 'bob@testpay', 14, 'normal');
              }}
              disabled={!!isSubmitting}
              className="text-left p-3.5 rounded-xl border border-emerald-200 bg-emerald-50/60 hover:bg-emerald-100/70 transition space-y-1.5 disabled:opacity-50"
            >
              <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-800">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                Scenario A: Normal ₹499
              </div>
              <p className="text-[11px] text-emerald-700 leading-snug">
                Alice paying Bob at 14:00. Standard amount, expected to auto-settle.
              </p>
            </button>

            {/* Scenario B */}
            <button
              onClick={() => {
                setSimulatedHour(14);
                handleBuy(85000, 'Unusual Large Transfer (Eve)', 'eve@testpay', 'mallory@testpay', 14, 'review');
              }}
              disabled={!!isSubmitting}
              className="text-left p-3.5 rounded-xl border border-amber-200 bg-amber-50/60 hover:bg-amber-100/70 transition space-y-1.5 disabled:opacity-50"
            >
              <div className="flex items-center gap-1.5 text-xs font-bold text-amber-800">
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                Scenario B: Large ₹85,000
              </div>
              <p className="text-[11px] text-amber-700 leading-snug">
                Eve paying Mallory. High balance drain, routes to Review Queue.
              </p>
            </button>

            {/* Scenario C */}
            <button
              onClick={() => {
                setSimulatedHour(2);
                handleBuy(12000, 'Suspicious 02:00 AM Transfer (Eve)', 'eve@testpay', 'mallory@testpay', 2, 'night_drain');
              }}
              disabled={!!isSubmitting}
              className="text-left p-3.5 rounded-xl border border-red-200 bg-red-50/60 hover:bg-red-100/70 transition space-y-1.5 disabled:opacity-50"
            >
              <div className="flex items-center gap-1.5 text-xs font-bold text-red-800">
                <span className="w-2 h-2 rounded-full bg-danger" />
                Scenario C: 02:00 AM Transfer
              </div>
              <p className="text-[11px] text-red-700 leading-snug">
                ₹12,000 sent at 2:00 AM off-hours from empty account.
              </p>
            </button>

            {/* Scenario D */}
            <button
              onClick={handleRapidRepeats}
              disabled={!!isSubmitting}
              className="text-left p-3.5 rounded-xl border border-purple-200 bg-purple-50/60 hover:bg-purple-100/70 transition space-y-1.5 disabled:opacity-50"
            >
              <div className="flex items-center gap-1.5 text-xs font-bold text-purple-800">
                <span className="w-2 h-2 rounded-full bg-primary" />
                Scenario D: Rapid 5-Repeat
              </div>
              <p className="text-[11px] text-purple-700 leading-snug">
                Velocity spike: 5 rapid ₹9,999 transfers in seconds.
              </p>
            </button>
          </div>

          {/* Status feedback */}
          {rapidStatus && (
            <div className="p-3 bg-purple-50 border border-purple-200 text-purple-800 rounded-lg text-xs font-medium flex items-center gap-2">
              <span className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span>{rapidStatus}</span>
            </div>
          )}

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 text-danger rounded-lg text-xs font-medium">
              {error}
            </div>
          )}
        </section>

        {/* Product Catalog Grid */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-base font-semibold text-text-primary">Featured Demo Products</h4>
            <span className="text-xs text-text-muted">Click &quot;Buy with UPI&quot; to launch hosted checkout</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {PRODUCTS.map((prod) => (
              <div
                key={prod.id}
                className="bg-bg-card rounded-xl border border-border-light shadow-card hover:shadow-card-hover transition p-5 flex flex-col justify-between space-y-4"
              >
                <div className="space-y-3">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                      {prod.icon}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-wider text-text-muted">
                      {prod.category}
                    </span>
                    <h5 className="text-base font-semibold text-text-primary mt-0.5">{prod.name}</h5>
                    <p className="text-xs text-text-secondary mt-1 leading-relaxed">{prod.description}</p>
                  </div>
                </div>

                <div className="pt-3 border-t border-border-light flex items-center justify-between">
                  <div className="text-lg font-bold text-text-primary font-mono">{formatCurrency(prod.price)}</div>
                  <button
                    onClick={() => handleBuy(prod.price, prod.name, 'alice@testpay', 'bob@testpay')}
                    disabled={!!isSubmitting}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-dark text-white text-xs font-semibold shadow-sm transition disabled:opacity-50"
                  >
                    {isSubmitting === prod.name ? (
                      <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <>
                        <span className="material-symbols-outlined text-base">shopping_cart_checkout</span>
                        <span>Buy with UPI</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Custom Transaction Generator */}
        <section className="bg-bg-card rounded-xl border border-border-light p-5 sm:p-6 shadow-card space-y-4">
          <div>
            <h4 className="text-base font-semibold text-text-primary">Custom Payment Intent Generator</h4>
            <p className="text-xs text-text-muted mt-0.5">
              Specify arbitrary amounts and accounts to test edge cases directly in the checkout flow.
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleBuy(customAmount, customDesc, customSender, customReceiver, simulatedHour);
            }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end"
          >
            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1">Amount (₹)</label>
              <input
                type="number"
                min="1"
                value={customAmount}
                onChange={(e) => setCustomAmount(Number(e.target.value))}
                required
                className="w-full px-3 py-2 rounded-lg border border-border-light text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1">Sender VPA</label>
              <input
                type="text"
                value={customSender}
                onChange={(e) => setCustomSender(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-lg border border-border-light text-xs font-mono text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1">Receiver VPA</label>
              <input
                type="text"
                value={customReceiver}
                onChange={(e) => setCustomReceiver(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-lg border border-border-light text-xs font-mono text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
              />
            </div>

            <div>
              <button
                type="submit"
                disabled={!!isSubmitting}
                className="w-full py-2 px-4 rounded-lg bg-primary hover:bg-primary-dark text-white text-xs font-semibold shadow-sm transition disabled:opacity-50 flex items-center justify-center gap-1.5 h-[34px]"
              >
                <span className="material-symbols-outlined text-base">bolt</span>
                <span>Generate Intent</span>
              </button>
            </div>
          </form>
        </section>
      </div>
    </AppShell>
  );
}
