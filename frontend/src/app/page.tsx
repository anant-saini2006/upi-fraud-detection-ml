'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import AppShell from '@/components/AppShell';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  api,
  type AmountDistribution,
  type FraudByHourRow,
  type FraudByTypeRow,
  type PredictionHistory,
  type Stats,
} from '@/lib/api';

type DashboardData = {
  stats: Stats | null;
  fraudByType: FraudByTypeRow[] | null;
  fraudByHour: FraudByHourRow[] | null;
  amountDistribution: AmountDistribution | null;
  predictionHistory: PredictionHistory | null;
};

type DashboardFailures = Record<keyof DashboardData, boolean>;

const emptyDashboardData = (): DashboardData => ({
  stats: null,
  fraudByType: null,
  fraudByHour: null,
  amountDistribution: null,
  predictionHistory: null,
});

const noFailures = (): DashboardFailures => ({
  stats: false,
  fraudByType: false,
  fraudByHour: false,
  amountDistribution: false,
  predictionHistory: false,
});

const tooltipStyle = {
  border: '1px solid #E5E7EB',
  borderRadius: 8,
  boxShadow: '0 8px 20px rgba(15, 23, 42, 0.10)',
  fontSize: 12,
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatNumber(value: unknown) {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
}

function formatCurrency(value: unknown) {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value: unknown) {
  if (!isFiniteNumber(value)) return '—';
  return `${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value)}%`;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function riskClass(risk: 'LOW' | 'MEDIUM' | 'HIGH') {
  if (risk === 'HIGH') return 'bg-red-50 text-red-700 border-red-200';
  if (risk === 'MEDIUM') return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-emerald-50 text-emerald-700 border-emerald-200';
}

function LoadingPanel({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-xl bg-gray-100 ${className}`} aria-label="Loading dashboard data" />
  );
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-8">
      <span className="material-symbols-outlined text-3xl text-text-muted mb-2">data_usage</span>
      <p className="text-xs text-text-muted leading-relaxed">{message}</p>
    </div>
  );
}

function UnavailableChart({ label }: { label: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-8">
      <span className="material-symbols-outlined text-3xl text-amber-500 mb-2">cloud_off</span>
      <p className="text-xs text-text-muted leading-relaxed">
        {label} could not be loaded. Refresh the dashboard to try again.
      </p>
    </div>
  );
}

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<DashboardData>(emptyDashboardData);
  const [failures, setFailures] = useState<DashboardFailures>(noFailures);
  const [isLoading, setIsLoading] = useState(true);
  const [isMounted, setIsMounted] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      setIsLoading(true);
      setDashboard(emptyDashboardData());
      setFailures(noFailures());

      const [stats, fraudByType, fraudByHour, amountDistribution, predictionHistory] = await Promise.allSettled([
        api.stats(),
        api.fraudByType(),
        api.fraudByHour(),
        api.amountDistribution(),
        api.recentPredictions(5),
      ] as const);

      if (cancelled) return;

      setDashboard({
        stats: stats.status === 'fulfilled' ? stats.value : null,
        fraudByType: fraudByType.status === 'fulfilled' ? fraudByType.value : null,
        fraudByHour: fraudByHour.status === 'fulfilled' ? fraudByHour.value : null,
        amountDistribution: amountDistribution.status === 'fulfilled' ? amountDistribution.value : null,
        predictionHistory: predictionHistory.status === 'fulfilled' ? predictionHistory.value : null,
      });
      setFailures({
        stats: stats.status === 'rejected',
        fraudByType: fraudByType.status === 'rejected',
        fraudByHour: fraudByHour.status === 'rejected',
        amountDistribution: amountDistribution.status === 'rejected',
        predictionHistory: predictionHistory.status === 'rejected',
      });
      setIsLoading(false);
    }

    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const pieData = useMemo(() => {
    if (!dashboard.stats) return [];

    return [
      { name: 'Legitimate', value: dashboard.stats.legit_count, color: '#6C63FF' },
      { name: 'Fraud', value: dashboard.stats.fraud_count, color: '#EF4444' },
    ].filter((item) => isFiniteNumber(item.value) && item.value > 0);
  }, [dashboard.stats]);

  const typeData = useMemo(() => {
    return [...(dashboard.fraudByType ?? [])]
      .filter((row) => isFiniteNumber(row.fraud) && row.fraud >= 0)
      .sort((a, b) => b.fraud - a.fraud);
  }, [dashboard.fraudByType]);

  const hourData = useMemo(() => {
    return [...(dashboard.fraudByHour ?? [])]
      .filter((row) => isFiniteNumber(row.hour) && isFiniteNumber(row.fraud_rate))
      .sort((a, b) => a.hour - b.hour);
  }, [dashboard.fraudByHour]);

  const amountData = useMemo(() => {
    if (!dashboard.amountDistribution) return [];

    const { legitimate, fraud } = dashboard.amountDistribution;
    return [
      { group: 'Legitimate', median: legitimate.median, mean: legitimate.mean },
      { group: 'Fraud', median: fraud.median, mean: fraud.mean },
    ].filter((row) => isFiniteNumber(row.median) || isFiniteNumber(row.mean));
  }, [dashboard.amountDistribution]);

  const hasAnyFailure = Object.values(failures).some(Boolean);
  const hasAnyData = Object.values(dashboard).some((value) => value !== null);
  const stats = dashboard.stats;
  const predictionHistory = dashboard.predictionHistory;
  const datasetSource = stats?.dataset_source ?? 'Dataset source unavailable';
  const usesSyntheticFixture = /synthetic|generated|development fixture/i.test(datasetSource);

  const kpis = stats
    ? [
        {
          label: 'Total Transactions',
          value: formatNumber(stats.total_transactions),
          subtext: 'Rows in the active dataset',
          icon: 'receipt_long',
          iconBg: 'bg-blue-100',
          iconColor: 'text-blue-600',
        },
        {
          label: 'Fraud-labelled Records',
          value: formatNumber(stats.fraud_count),
          subtext: 'Records labelled as fraud',
          icon: 'gpp_bad',
          iconBg: 'bg-red-100',
          iconColor: 'text-red-600',
        },
        {
          label: 'Fraud Rate',
          value: formatPercent(stats.fraud_rate),
          subtext: 'Share of fraud-labelled records',
          icon: 'percent',
          iconBg: 'bg-purple-100',
          iconColor: 'text-purple-600',
        },
        {
          label: 'Average Amount',
          value: formatCurrency(stats.avg_amount),
          subtext: 'Dataset-wide transaction mean',
          icon: 'currency_rupee',
          iconBg: 'bg-orange-100',
          iconColor: 'text-orange-600',
        },
      ]
    : [];

  if (!isLoading && !hasAnyData && hasAnyFailure) {
    return (
      <AppShell>
        <div className="min-h-[60vh] flex items-center justify-center">
          <div className="max-w-md text-center bg-bg-card border border-border-light rounded-xl p-8 shadow-card">
            <span className="material-symbols-outlined text-4xl text-amber-500 mb-3">cloud_off</span>
            <h3 className="text-lg font-semibold text-text-primary">Dashboard data is unavailable</h3>
            <p className="mt-2 text-sm text-text-secondary leading-relaxed">
              The dataset API could not be reached. Confirm that the inference API is running and that
              <code className="mx-1 text-xs bg-gray-100 px-1.5 py-0.5 rounded">NEXT_PUBLIC_API_URL</code>
              is configured correctly, then try again.
            </p>
            <button
              type="button"
              onClick={() => setReloadKey((key) => key + 1)}
              className="mt-5 inline-flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark transition-colors"
            >
              <span className="material-symbols-outlined text-base">refresh</span>
              Retry
            </button>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <section className="bg-primary/5 border border-primary/15 rounded-xl p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              Real-Time Payment Security
            </p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">UPI Fraud Detection & Risk Analytics</h3>
            <p className="mt-1 max-w-3xl text-sm text-text-secondary leading-relaxed">
              Real-time analytics and machine learning risk classification across digital payment transactions. Monitor transaction volume, anomaly distributions, and model performance.
            </p>
          </div>
          <Link
            href="/predict"
            className="shrink-0 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark transition-colors shadow-sm"
          >
            <span className="material-symbols-outlined text-lg">bolt</span>
            Instant prediction
          </Link>
        </section>

        {hasAnyFailure && hasAnyData && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined text-amber-600 text-lg mt-0.5">warning</span>
              <p className="text-sm text-amber-900">
                Some dataset visualizations are unavailable right now. The loaded sections still reflect live API data.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setReloadKey((key) => key + 1)}
              className="shrink-0 text-sm font-medium text-amber-900 hover:text-amber-700"
            >
              Refresh data
            </button>
          </div>
        )}

        <section aria-label="Dataset key performance indicators" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {isLoading && Array.from({ length: 4 }, (_, index) => <LoadingPanel key={index} className="h-[132px]" />)}

          {!isLoading && failures.stats && (
            <div className="sm:col-span-2 lg:col-span-4 bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
              <UnavailableChart label="Dataset KPI data" />
            </div>
          )}

          {!isLoading && !failures.stats && kpis.map((kpi) => (
            <article key={kpi.label} className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card hover:shadow-card-hover transition-shadow">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-text-muted uppercase tracking-wider">{kpi.label}</p>
                  <p className="text-2xl font-bold text-text-primary mt-1">{kpi.value}</p>
                  <p className="text-xs text-text-muted mt-1">{kpi.subtext}</p>
                </div>
                <div className={`w-10 h-10 rounded-xl ${kpi.iconBg} flex items-center justify-center`}>
                  <span className={`material-symbols-outlined ${kpi.iconColor} text-xl`} style={{ fontVariationSettings: "'FILL' 1" }}>
                    {kpi.icon}
                  </span>
                </div>
              </div>
            </article>
          ))}
        </section>

        {stats && !isLoading && !failures.stats && (
          <section className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-text-muted px-1" aria-label="Dataset metadata">
            <span>Maximum observed amount: <strong className="font-semibold text-text-secondary">{formatCurrency(stats.max_amount)}</strong></span>
            <span>
              Model selected during training: <strong className="font-semibold text-text-secondary">{stats.model_name || 'Unavailable'}</strong>
            </span>
          </section>
        )}

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary">Fraud vs legitimate</h3>
            <p className="mt-1 text-xs text-text-muted">Class balance in the active dataset</p>
            <div className="h-60 relative mt-2">
              {isLoading ? <LoadingPanel className="h-full" /> : failures.stats ? (
                <UnavailableChart label="Class-balance data" />
              ) : pieData.length === 0 ? (
                <EmptyChart message="No class-balance records are available in this dataset." />
              ) : isMounted ? (
                <>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={pieData} cx="50%" cy="48%" innerRadius={60} outerRadius={88} paddingAngle={3} dataKey="value" stroke="none">
                        {pieData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                      </Pie>
                      <Tooltip
                        contentStyle={tooltipStyle}
                        formatter={(value: number) => [formatNumber(value), 'Records']}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none" style={{ marginTop: '-20px' }}>
                    <span className="text-xl font-bold text-text-primary">{formatPercent(stats?.fraud_rate)}</span>
                    <span className="text-[10px] text-text-muted uppercase tracking-wider">Fraud rate</span>
                  </div>
                  <div className="absolute bottom-0 inset-x-0 flex justify-center gap-4 text-xs text-text-secondary">
                    {pieData.map((entry) => (
                      <span key={entry.name} className="inline-flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
                        {entry.name}
                      </span>
                    ))}
                  </div>
                </>
              ) : <LoadingPanel className="h-full" />}
            </div>
          </article>

          <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary">Fraud records by transaction type</h3>
            <p className="mt-1 text-xs text-text-muted">Count of fraud-labelled records per type</p>
            <div className="h-60 mt-2">
              {isLoading ? <LoadingPanel className="h-full" /> : failures.fraudByType ? (
                <UnavailableChart label="Transaction-type data" />
              ) : typeData.length === 0 ? (
                <EmptyChart message="No transaction-type records are available in this dataset." />
              ) : isMounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={typeData} margin={{ top: 8, right: 6, left: -18, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                    <XAxis dataKey="type" fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} />
                    <YAxis fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} tickFormatter={formatNumber} />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      formatter={(value: number) => [formatNumber(value), 'Fraud records']}
                    />
                    <Bar dataKey="fraud" name="Fraud records" fill="#6C63FF" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <LoadingPanel className="h-full" />}
            </div>
          </article>

          <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary">Fraud rate by hour of day</h3>
            <p className="mt-1 text-xs text-text-muted">Percentage of records labelled as fraud per hour</p>
            <div className="h-60 mt-2">
              {isLoading ? <LoadingPanel className="h-full" /> : failures.fraudByHour ? (
                <UnavailableChart label="Hourly fraud-rate data" />
              ) : hourData.length === 0 ? (
                <EmptyChart message="No hourly fraud-rate records are available in this dataset." />
              ) : isMounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={hourData} margin={{ top: 8, right: 6, left: -18, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                    <XAxis
                      dataKey="hour"
                      fontSize={10}
                      stroke="#9CA3AF"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(hour: number) => `${hour}:00`}
                    />
                    <YAxis
                      fontSize={10}
                      stroke="#9CA3AF"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value: number) => `${value}%`}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      labelFormatter={(hour) => `${hour}:00`}
                      formatter={(value: number) => [formatPercent(value), 'Fraud rate']}
                    />
                    <Line type="monotone" dataKey="fraud_rate" name="Fraud rate" stroke="#6C63FF" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <LoadingPanel className="h-full" />}
            </div>
          </article>
        </section>

        <section className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-text-primary">Transaction amount summary</h3>
              <p className="mt-1 text-xs text-text-muted">
                Mean and median amounts by class; values above the dataset&apos;s 99th-percentile cap are excluded.
              </p>
            </div>
            {dashboard.amountDistribution && amountData.length > 0 && (
              <div className="flex gap-3 text-xs text-text-secondary">
                <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-primary" />Median</span>
                <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-orange-400" />Mean</span>
              </div>
            )}
          </div>
          <div className="h-64 mt-4">
            {isLoading ? <LoadingPanel className="h-full" /> : failures.amountDistribution ? (
              <UnavailableChart label="Amount-distribution data" />
            ) : amountData.length === 0 ? (
              <EmptyChart message="No amount summary is available for the classes in this dataset." />
            ) : isMounted ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={amountData} margin={{ top: 8, right: 12, left: -4, bottom: 5 }} barGap={6}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                  <XAxis dataKey="group" fontSize={11} stroke="#9CA3AF" tickLine={false} axisLine={false} />
                  <YAxis fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} tickFormatter={(value: number) => formatCurrency(value)} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value: number, name: string) => [formatCurrency(value), name]}
                  />
                  <Bar dataKey="median" name="Median" fill="#6C63FF" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="mean" name="Mean" fill="#F59E0B" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <LoadingPanel className="h-full" />}
          </div>
        </section>

        <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border-light flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-text-primary">Recent prediction history</h3>
              <p className="mt-1 text-xs text-text-muted">Live model inference records persisted to PostgreSQL database.</p>
            </div>
            {predictionHistory?.persistence.configured ? (
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                <span className="material-symbols-outlined text-sm">database</span>
                PostgreSQL history enabled
              </span>
            ) : (
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                <span className="material-symbols-outlined text-sm">database_off</span>
                PostgreSQL not configured
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="p-5"><LoadingPanel className="h-32" /></div>
          ) : failures.predictionHistory ? (
            <div className="h-36"><UnavailableChart label="Prediction history" /></div>
          ) : !predictionHistory?.persistence.configured ? (
            <div className="px-5 py-8 text-center">
              <p className="text-sm text-text-secondary">Add a Neon/PostgreSQL <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">DATABASE_URL</code> to the API to persist and display recent predictions.</p>
            </div>
          ) : predictionHistory.predictions.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-text-secondary">No predictions have been recorded yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[670px] text-sm">
                <thead>
                  <tr className="bg-gray-50 text-left text-[11px] uppercase tracking-wider text-text-muted">
                    <th className="px-5 py-3 font-medium">Time</th>
                    <th className="px-5 py-3 font-medium">Type</th>
                    <th className="px-5 py-3 font-medium">Amount</th>
                    <th className="px-5 py-3 font-medium">Result</th>
                    <th className="px-5 py-3 font-medium">Probability</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light">
                  {predictionHistory.predictions.map((prediction) => (
                    <tr key={prediction.id} className="hover:bg-gray-50/60">
                      <td className="px-5 py-3 text-xs text-text-secondary">{formatDateTime(prediction.created_at)}</td>
                      <td className="px-5 py-3 font-mono text-xs text-text-secondary">{prediction.transaction_type}</td>
                      <td className="px-5 py-3 font-medium text-text-primary">{formatCurrency(prediction.amount)}</td>
                      <td className="px-5 py-3">
                        <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-semibold ${riskClass(prediction.risk_level)}`}>
                          {prediction.prediction} · {prediction.risk_level}
                        </span>
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-text-secondary">{formatPercent(prediction.fraud_probability * 100)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
