'use client';

import { useEffect, useState } from 'react';
import { api, ThresholdSettings, AccountInfo } from '@/lib/api';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<ThresholdSettings>({
    block_threshold: 0.70,
    review_threshold: 0.30,
  });
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    let isMounted = true;
    Promise.all([api.adminGetSettings(), api.adminListAccounts()])
      .then(([s, a]) => {
        if (isMounted) {
          setSettings(s);
          setAccounts(a.accounts || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setMessage({ text: err.message || 'Failed to load policy configuration', type: 'error' });
          setLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (settings.review_threshold >= settings.block_threshold) {
      setMessage({
        text: 'Review threshold must be strictly less than Block threshold.',
        type: 'error',
      });
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      const updated = await api.adminUpdateSettings(settings);
      setSettings(updated);
      setMessage({ text: 'Decision thresholds updated live in the PostgreSQL database!', type: 'success' });
    } catch (err: unknown) {
      setMessage({
        text: err instanceof Error ? err.message : 'Failed to update thresholds',
        type: 'error',
      });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  if (loading) {
    return (
      <div className="bg-bg-card rounded-xl border border-border-light p-12 text-center text-text-muted text-sm shadow-card">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        Loading policy configuration and ledger state...
      </div>
    );
  }

  const reviewPct = Math.round(settings.review_threshold * 100);
  const blockPct = Math.round(settings.block_threshold * 100);

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Hero Banner */}
      <section className="bg-primary/5 border border-primary/15 rounded-xl p-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">Risk Decision Engine</p>
        <h3 className="mt-1 text-xl font-semibold text-text-primary">Policy Thresholds & Simulated Ledger</h3>
        <p className="mt-1 max-w-3xl text-sm text-text-secondary leading-relaxed">
          Tune the operational cutoffs dividing automated settlements from human review escrows and hard declines.
          Changes take effect immediately on incoming gateway payments.
        </p>
      </section>

      {/* Message alert */}
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

      {/* Threshold Sliders Card */}
      <form onSubmit={handleSave} className="bg-bg-card border border-border-light rounded-xl p-5 sm:p-6 shadow-card space-y-6">
        <div>
          <h4 className="text-base font-semibold text-text-primary">Decision Threshold Sliders</h4>
          <p className="mt-1 text-sm text-text-secondary">
            Set the fraud probability percentage boundaries for transaction processing.
          </p>
        </div>

        {/* Visual Spectrum */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs font-semibold text-text-secondary">
            <span>0% Probability</span>
            <span>100% Probability</span>
          </div>

          <div className="h-6 w-full rounded-lg overflow-hidden flex text-[10px] font-bold text-white shadow-inner">
            <div
              style={{ width: `${reviewPct}%` }}
              className="bg-emerald-500 flex items-center justify-center transition-all"
              title={`Approve: 0% to ${reviewPct}%`}
            >
              {reviewPct >= 15 ? 'AUTO-APPROVE' : ''}
            </div>
            <div
              style={{ width: `${blockPct - reviewPct}%` }}
              className="bg-amber-500 flex items-center justify-center transition-all text-neutral-900"
              title={`Review: ${reviewPct}% to ${blockPct}%`}
            >
              {blockPct - reviewPct >= 15 ? 'HUMAN REVIEW' : ''}
            </div>
            <div
              style={{ width: `${100 - blockPct}%` }}
              className="bg-red-500 flex items-center justify-center transition-all"
              title={`Block: ${blockPct}% to 100%`}
            >
              {100 - blockPct >= 15 ? 'AUTO-BLOCK' : ''}
            </div>
          </div>

          <div className="flex justify-between text-xs text-text-muted">
            <span className="text-emerald-700 font-medium">Safe Zone (&lt; {reviewPct}%)</span>
            <span className="text-amber-700 font-medium">Escrow Review ({reviewPct}% – {blockPct}%)</span>
            <span className="text-red-700 font-medium">Decline Zone (&gt; {blockPct}%)</span>
          </div>
        </div>

        {/* Sliders Input Controls */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
          {/* Review Threshold Slider */}
          <div className="bg-gray-50 border border-border-light rounded-xl p-4 space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Review Threshold (Escrow Trigger)
              </label>
              <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-mono font-bold text-xs">
                {settings.review_threshold.toFixed(2)} ({reviewPct}%)
              </span>
            </div>
            <input
              type="range"
              min="0.05"
              max="0.90"
              step="0.01"
              value={settings.review_threshold}
              onChange={(e) =>
                setSettings((prev) => ({
                  ...prev,
                  review_threshold: parseFloat(e.target.value),
                }))
              }
              className="w-full accent-amber-500 cursor-pointer"
            />
            <p className="text-[11px] text-text-muted">
              Transactions exceeding this risk level will NOT be settled immediately; they are routed to the review queue.
            </p>
          </div>

          {/* Block Threshold Slider */}
          <div className="bg-gray-50 border border-border-light rounded-xl p-4 space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Block Threshold (Hard Decline)
              </label>
              <span className="px-2 py-0.5 rounded bg-red-100 text-red-800 font-mono font-bold text-xs">
                {settings.block_threshold.toFixed(2)} ({blockPct}%)
              </span>
            </div>
            <input
              type="range"
              min="0.10"
              max="0.95"
              step="0.01"
              value={settings.block_threshold}
              onChange={(e) =>
                setSettings((prev) => ({
                  ...prev,
                  block_threshold: parseFloat(e.target.value),
                }))
              }
              className="w-full accent-red-500 cursor-pointer"
            />
            <p className="text-[11px] text-text-muted">
              Transactions exceeding this risk level are immediately declined and flagged as confirmed fraud attempts.
            </p>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-dark text-white font-medium text-sm rounded-lg shadow-sm transition disabled:opacity-50"
          >
            {saving ? (
              <>
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Saving Settings...</span>
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-lg">save</span>
                <span>Save Decision Thresholds</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Simulated Ledger Accounts */}
      <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border-light flex items-center justify-between">
          <div>
            <h4 className="text-base font-semibold text-text-primary">Simulated VPA Wallets (Neon Postgres Ledger)</h4>
            <p className="mt-0.5 text-xs text-text-muted">
              Live balances stored in the accounts table. Balances deduct on sender approval and credit receiver accounts.
            </p>
          </div>
          <span className="text-xs font-mono px-2 py-1 bg-gray-100 text-text-secondary rounded">
            {accounts.length} Test VPAs
          </span>
        </div>

        {accounts.length === 0 ? (
          <div className="p-8 text-center text-text-muted text-sm">
            No simulated accounts discovered in database. Click &quot;Reset Demo&quot; to seed initial test VPAs.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="bg-gray-50 text-[11px] uppercase tracking-wider text-text-muted border-b border-border-light">
                  <th className="px-5 py-3 font-medium">Virtual Payment Address (VPA)</th>
                  <th className="px-5 py-3 font-medium">Account Owner</th>
                  <th className="px-5 py-3 font-medium text-right">Current Balance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-light">
                {accounts.map((acc) => (
                  <tr key={acc.vpa} className="hover:bg-gray-50/60">
                    <td className="px-5 py-3 font-mono text-xs font-semibold text-text-primary">
                      {acc.vpa}
                    </td>
                    <td className="px-5 py-3 text-xs text-text-secondary">
                      {acc.vpa.startsWith('alice') && 'Alice (Normal Consumer)'}
                      {acc.vpa.startsWith('bob') && 'Bob (Merchant Partner)'}
                      {acc.vpa.startsWith('eve') && 'Eve (High-Velocity Test Payer)'}
                      {acc.vpa.startsWith('mallory') && 'Mallory (Mule Destination Account)'}
                      {!['alice', 'bob', 'eve', 'mallory'].some((prefix) => acc.vpa.startsWith(prefix)) &&
                        'Simulated Customer Account'}
                    </td>
                    <td className="px-5 py-3 font-mono font-bold text-text-primary text-right">
                      {formatCurrency(acc.wallet_balance)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
