'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
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
    second: '2-digit',
    day: 'numeric',
    month: 'short',
  }).format(d);
}

function statusBadge(status: string) {
  if (status === 'succeeded') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
        Succeeded
      </span>
    );
  }
  if (status === 'requires_review') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
        Needs Review
      </span>
    );
  }
  if (status === 'blocked') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
        Blocked
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-50 text-text-secondary border border-border-light">
      {status}
    </span>
  );
}

function riskBadge(scoring?: PaymentIntent['scoring']) {
  if (!scoring) return <span className="text-xs text-text-muted">—</span>;
  const { risk_band, probability } = scoring;
  const pct = Math.round(probability * 100);

  let style = 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (risk_band === 'HIGH') style = 'bg-red-50 text-red-700 border-red-200';
  else if (risk_band === 'MEDIUM') style = 'bg-amber-50 text-amber-700 border-amber-200';

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border font-mono ${style}`}>
      <span>{risk_band}</span>
      <span className="opacity-75">({pct}%)</span>
    </span>
  );
}

export default function AdminLiveFeedPage() {
  const [payments, setPayments] = useState<PaymentIntent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [search, setSearch] = useState<string>('');

  const fetchPayments = useCallback(async () => {
    try {
      const filter = statusFilter === 'all' ? undefined : statusFilter;
      const res = await api.adminListPayments(100, filter);
      setPayments(res.payments || []);
    } catch {
      // Ignore background errors
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchPayments();
    const interval = setInterval(fetchPayments, 3500);

    const onUpdate = () => fetchPayments();
    window.addEventListener('payments-updated', onUpdate);

    return () => {
      clearInterval(interval);
      window.removeEventListener('payments-updated', onUpdate);
    };
  }, [fetchPayments]);

  const filtered = useMemo(() => {
    return payments.filter((p) => {
      if (!search.trim()) return true;
      const term = search.toLowerCase();
      return (
        p.id.toLowerCase().includes(term) ||
        p.sender_vpa.toLowerCase().includes(term) ||
        p.receiver_vpa.toLowerCase().includes(term) ||
        (p.description && p.description.toLowerCase().includes(term))
      );
    });
  }, [payments, search]);

  // Aggregate metrics
  const stats = useMemo(() => {
    const totalCount = payments.length;
    const totalVolume = payments.reduce((acc, p) => acc + (p.status === 'succeeded' ? p.amount : 0), 0);
    const succeededCount = payments.filter((p) => p.status === 'succeeded').length;
    const reviewCount = payments.filter((p) => p.status === 'requires_review').length;
    const blockedCount = payments.filter((p) => p.status === 'blocked').length;
    return { totalCount, totalVolume, succeededCount, reviewCount, blockedCount };
  }, [payments]);

  return (
    <div className="space-y-6">
      {/* Hero Header */}
      <section className="bg-primary/5 border border-primary/15 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">Live Payment Stream</p>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live 3.5s
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold text-text-primary">Real-time Gateway Telemetry</h3>
          <p className="mt-1 max-w-3xl text-sm text-text-secondary leading-relaxed">
            Real-time transaction stream passing through the Stripe-style gateway API and scored against the ML decision policy.
          </p>
        </div>
        <Link
          href="/shop"
          className="shrink-0 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark transition-colors shadow-sm"
        >
          <span className="material-symbols-outlined text-lg">storefront</span>
          Open Demo Store
        </Link>
      </section>

      {/* KPI Stats Cards */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card hover:shadow-card-hover transition-shadow">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider">Total Volume</p>
              <p className="text-2xl font-bold text-text-primary mt-1">{formatCurrency(stats.totalVolume)}</p>
              <p className="text-xs text-text-muted mt-1">{stats.totalCount} total intents captured</p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
              <span className="material-symbols-outlined text-blue-600 text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                receipt_long
              </span>
            </div>
          </div>
        </article>

        <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card hover:shadow-card-hover transition-shadow">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider">Settled Clean</p>
              <p className="text-2xl font-bold text-text-primary mt-1">{stats.succeededCount}</p>
              <p className="text-xs text-text-muted mt-1">Instant ledger settlements</p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
              <span className="material-symbols-outlined text-emerald-600 text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                check_circle
              </span>
            </div>
          </div>
        </article>

        <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card hover:shadow-card-hover transition-shadow">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider">Requires Review</p>
              <p className="text-2xl font-bold text-amber-600 mt-1">{stats.reviewCount}</p>
              <p className="text-xs text-text-muted mt-1">Held in analyst queue</p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
              <span className="material-symbols-outlined text-amber-600 text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                pending_actions
              </span>
            </div>
          </div>
        </article>

        <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card hover:shadow-card-hover transition-shadow">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider">Blocked (Fraud)</p>
              <p className="text-2xl font-bold text-danger mt-1">{stats.blockedCount}</p>
              <p className="text-xs text-text-muted mt-1">High-risk declines</p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center">
              <span className="material-symbols-outlined text-red-600 text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                gpp_bad
              </span>
            </div>
          </div>
        </article>
      </section>

      {/* Filter and Table Container */}
      <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
        {/* Filter Controls Header */}
        <div className="p-4 sm:p-5 border-b border-border-light flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          {/* Search Box */}
          <div className="relative flex-1 max-w-md">
            <span className="material-symbols-outlined text-text-muted text-lg absolute left-3 top-2.5">
              search
            </span>
            <input
              type="text"
              placeholder="Search by ID, sender, receiver, note..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3.5 py-2 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
            />
          </div>

          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-lg">
            {[
              { label: 'All', value: 'all' },
              { label: 'Succeeded', value: 'succeeded' },
              { label: 'Review', value: 'requires_review' },
              { label: 'Blocked', value: 'blocked' },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => {
                  setStatusFilter(f.value);
                  setLoading(true);
                }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  statusFilter === f.value
                    ? 'bg-white text-text-primary shadow-sm font-semibold'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Transactions Table */}
        {loading && payments.length === 0 ? (
          <div className="p-12 text-center text-text-muted text-sm">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            Loading transaction telemetry...
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-text-muted text-sm space-y-2">
            <span className="material-symbols-outlined text-3xl text-text-muted">receipt</span>
            <p className="font-medium text-text-primary">No transactions found</p>
            <p className="text-xs">Try clearing the search query or use &quot;Simulate 50&quot; above to generate test payments.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm text-left">
              <thead>
                <tr className="bg-gray-50 text-[11px] uppercase tracking-wider text-text-muted border-b border-border-light">
                  <th className="px-5 py-3 font-medium">Timestamp</th>
                  <th className="px-5 py-3 font-medium">Payment ID</th>
                  <th className="px-5 py-3 font-medium">Flow (VPA)</th>
                  <th className="px-5 py-3 font-medium">Amount</th>
                  <th className="px-5 py-3 font-medium">ML Score</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-light">
                {filtered.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50/70 transition-colors">
                    <td className="px-5 py-3 text-xs text-text-secondary whitespace-nowrap">
                      {formatDateTime(p.created_at)}
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-text-primary">
                      <Link
                        href={`/admin/payments/${p.id}`}
                        className="hover:text-primary hover:underline font-semibold"
                        title={p.id}
                      >
                        {p.id.substring(0, 14)}...
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-xs font-mono text-text-secondary whitespace-nowrap">
                      <span className="text-text-primary font-medium">{p.sender_vpa}</span>
                      <span className="text-text-muted mx-1">→</span>
                      <span>{p.receiver_vpa}</span>
                    </td>
                    <td className="px-5 py-3 font-semibold text-text-primary whitespace-nowrap">
                      {formatCurrency(p.amount)}
                    </td>
                    <td className="px-5 py-3 whitespace-nowrap">
                      {riskBadge(p.scoring)}
                    </td>
                    <td className="px-5 py-3 whitespace-nowrap">
                      {statusBadge(p.status)}
                    </td>
                    <td className="px-5 py-3 text-right whitespace-nowrap">
                      <Link
                        href={`/admin/payments/${p.id}`}
                        className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary-dark transition"
                      >
                        <span>Inspect</span>
                        <span className="material-symbols-outlined text-sm">arrow_forward</span>
                      </Link>
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
