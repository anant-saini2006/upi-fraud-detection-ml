'use client';

import { useEffect, useMemo, useState } from 'react';
import AppShell from '@/components/AppShell';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, type ModelComparison, type PerformanceData } from '@/lib/api';

const tooltipStyle = {
  border: '1px solid #E5E7EB',
  borderRadius: 8,
  boxShadow: '0 8px 20px rgba(15, 23, 42, 0.10)',
  fontSize: 12,
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatCount(value: unknown): string {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
}

function formatRatio(value: unknown, fractionDigits = 2): string {
  if (!isFiniteNumber(value)) return '—';
  return `${new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value * 100)}%`;
}

function formatImportance(value: unknown): string {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: 4,
  }).format(value);
}

function LoadingBlock({ className = '' }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-xl bg-gray-100 ${className}`}
      aria-label="Loading model performance data"
    />
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-7 text-center">
      <span className="material-symbols-outlined text-3xl text-text-muted mb-2">data_usage</span>
      <p className="text-xs text-text-muted leading-relaxed">{message}</p>
    </div>
  );
}

function normaliseName(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function isSelectedModel(row: ModelComparison, bestModelName: string): boolean {
  return normaliseName(row.Model) === normaliseName(bestModelName);
}

export default function ModelPerformance() {
  const [performance, setPerformance] = useState<PerformanceData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPerformance() {
      setIsLoading(true);
      setError(null);
      setPerformance(null);

      try {
        const result = await api.performance();
        if (!cancelled) setPerformance(result);
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : 'The model-performance endpoint could not be reached.',
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadPerformance();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const rocData = useMemo(() => {
    return (performance?.roc_curve ?? [])
      .filter((point) => isFiniteNumber(point.fpr) && isFiniteNumber(point.tpr))
      .map((point) => ({
        fpr: point.fpr,
        tpr: point.tpr,
        baseline: point.fpr,
      }))
      .sort((left, right) => left.fpr - right.fpr);
  }, [performance]);

  const featureData = useMemo(() => {
    return (performance?.feature_importances ?? [])
      .filter((feature) => isFiniteNumber(feature.importance))
      .sort((left, right) => right.importance - left.importance)
      .slice(0, 12);
  }, [performance]);

  const comparisonRows = performance?.model_comparison ?? [];
  const metrics = performance?.metrics;

  const primaryMetrics = metrics
    ? [
        {
          label: 'Recall',
          value: formatRatio(metrics.recall),
          description: 'Fraud cases the model identifies',
          icon: 'radar',
          iconBg: 'bg-red-100',
          iconColor: 'text-red-600',
        },
        {
          label: 'Precision',
          value: formatRatio(metrics.precision),
          description: 'Fraud alerts that are correct',
          icon: 'verified',
          iconBg: 'bg-blue-100',
          iconColor: 'text-blue-600',
        },
        {
          label: 'F1 score',
          value: formatRatio(metrics.f1),
          description: 'Balance of precision and recall',
          icon: 'balance',
          iconBg: 'bg-purple-100',
          iconColor: 'text-purple-600',
        },
        {
          label: 'ROC-AUC',
          value: formatRatio(metrics.roc_auc),
          description: 'Ranking performance across thresholds',
          icon: 'timeline',
          iconBg: 'bg-orange-100',
          iconColor: 'text-orange-600',
        },
      ]
    : [];

  if (!isLoading && error && !performance) {
    return (
      <AppShell>
        <div className="min-h-[60vh] flex items-center justify-center">
          <div className="max-w-md bg-bg-card border border-border-light rounded-xl p-8 shadow-card text-center">
            <span className="material-symbols-outlined text-4xl text-amber-500 mb-3">cloud_off</span>
            <h3 className="text-lg font-semibold text-text-primary">Model performance is unavailable</h3>
            <p className="mt-2 text-sm text-text-secondary leading-relaxed">
              The saved model or its evaluation data could not be loaded from the inference API.
            </p>
            <p className="mt-2 text-xs text-text-muted break-words">{error}</p>
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
        <section className="bg-primary/5 border border-primary/15 rounded-xl p-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">Saved-model evaluation</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">
              {isLoading ? 'Loading evaluation results…' : `${performance?.best_model_name ?? 'Saved model'} performance`}
            </h3>
            <p className="mt-1 max-w-3xl text-sm text-text-secondary leading-relaxed">
              These are offline results from the saved model on the API&apos;s deterministic held-out test split.
              They support a UPI-style fraud-detection prototype; they are not live UPI-network performance metrics.
            </p>
          </div>
          {!isLoading && performance?.best_model_name && (
            <span className="inline-flex w-fit shrink-0 items-center gap-1.5 px-3 py-1.5 bg-white border border-primary/20 text-primary rounded-full text-xs font-semibold">
              <span className="material-symbols-outlined text-sm">workspace_premium</span>
              Selected: {performance.best_model_name}
            </span>
          )}
        </section>

        <section aria-label="Primary evaluation metrics" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {isLoading && Array.from({ length: 4 }, (_, index) => <LoadingBlock key={index} className="h-[126px]" />)}
          {!isLoading && primaryMetrics.map((metric) => (
            <article key={metric.label} className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-text-muted uppercase tracking-wider">{metric.label}</p>
                  <p className="mt-1 text-2xl font-bold text-text-primary">{metric.value}</p>
                  <p className="mt-1 text-xs text-text-muted">{metric.description}</p>
                </div>
                <div className={`w-10 h-10 rounded-xl ${metric.iconBg} flex items-center justify-center`}>
                  <span
                    className={`material-symbols-outlined text-xl ${metric.iconColor}`}
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    {metric.icon}
                  </span>
                </div>
              </div>
            </article>
          ))}
        </section>

        {!isLoading && performance && (
          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <article className="bg-amber-50 border border-amber-200 rounded-xl p-5">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-amber-700">info</span>
                <div>
                  <h3 className="text-sm font-semibold text-amber-950">Why accuracy is not the headline</h3>
                  <p className="mt-1 text-sm text-amber-900 leading-relaxed">
                    Fraud data is usually imbalanced, so a model can achieve high accuracy by predicting mostly
                    legitimate transactions. Recall, precision, F1, and ROC-AUC show fraud-detection quality more
                    honestly. Accuracy is retained in the comparison table for context: {formatRatio(metrics?.accuracy)}.
                  </p>
                </div>
              </div>
            </article>

            <article className="bg-bg-card border border-border-light rounded-xl p-5">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-text-secondary">fact_check</span>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Current evaluation caveat</h3>
                  <p className="mt-1 text-sm text-text-secondary leading-relaxed">
                    {performance.evaluation_note || 'The API did not provide an additional evaluation note.'}
                  </p>
                </div>
              </div>
            </article>
          </section>
        )}

        <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border-light flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-text-primary">Model comparison</h3>
              <p className="mt-1 text-xs text-text-muted">
                Training-time comparison returned by the API. Values are ratios displayed as percentages.
              </p>
            </div>
            {!isLoading && performance?.selection_rationale && (
              <p className="max-w-lg text-xs text-text-secondary leading-relaxed sm:text-right">
                <span className="font-semibold text-text-primary">Selection rationale:</span> {performance.selection_rationale}
              </p>
            )}
          </div>

          {isLoading ? (
            <div className="p-5 space-y-3">
              {Array.from({ length: 4 }, (_, index) => <LoadingBlock key={index} className="h-10" />)}
            </div>
          ) : comparisonRows.length === 0 ? (
            <div className="h-44"><EmptyPanel message="The API has not supplied a model comparison yet." /></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-text-muted text-xs uppercase tracking-wider">
                    <th scope="col" className="text-left px-5 py-3 font-medium">Model</th>
                    <th scope="col" className="text-left px-5 py-3 font-medium">Accuracy</th>
                    <th scope="col" className="text-left px-5 py-3 font-medium">Precision</th>
                    <th scope="col" className="text-left px-5 py-3 font-medium">Recall</th>
                    <th scope="col" className="text-left px-5 py-3 font-medium">F1 score</th>
                    <th scope="col" className="text-left px-5 py-3 font-medium">ROC-AUC</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light">
                  {comparisonRows.map((row) => {
                    const selected = isSelectedModel(row, performance?.best_model_name ?? '');
                    return (
                      <tr key={row.Model} className={selected ? 'bg-primary/5' : 'hover:bg-gray-50/50'}>
                        <td className="px-5 py-3 font-medium text-text-primary">
                          <div className="flex items-center gap-2">
                            {row.Model}
                            {selected && (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-semibold rounded bg-primary/10 text-primary">
                                <span className="material-symbols-outlined text-[12px]">check</span>
                                Selected
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-5 py-3 font-mono text-xs text-text-secondary">{formatRatio(row.Accuracy)}</td>
                        <td className="px-5 py-3 font-mono text-xs text-text-secondary">{formatRatio(row.Precision)}</td>
                        <td className="px-5 py-3 font-mono text-xs text-text-secondary">{formatRatio(row.Recall)}</td>
                        <td className="px-5 py-3 font-mono text-xs text-text-secondary">{formatRatio(row.F1)}</td>
                        <td className="px-5 py-3 font-mono text-xs text-text-secondary">{formatRatio(row['ROC-AUC'])}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary">Confusion matrix</h3>
            <p className="mt-1 text-xs text-text-muted">Saved model at the evaluation threshold.</p>

            <div className="mt-5 space-y-2">
              {isLoading ? <LoadingBlock className="h-44" /> : performance ? (
                <>
                  <div className="grid grid-cols-[72px_1fr_1fr] gap-2 text-center">
                    <span />
                    <span className="text-[10px] text-text-muted uppercase tracking-wider">Predicted legitimate</span>
                    <span className="text-[10px] text-text-muted uppercase tracking-wider">Predicted fraud</span>

                    <span className="self-center text-right text-[10px] text-text-muted uppercase tracking-wider">Actual legitimate</span>
                    <div className="rounded-lg bg-green-100 p-3">
                      <p className="text-lg font-bold text-green-700">{formatCount(performance.confusion_matrix.tn)}</p>
                      <p className="text-[10px] text-green-700/75">True negative</p>
                    </div>
                    <div className="rounded-lg bg-red-50 p-3">
                      <p className="text-lg font-bold text-red-500">{formatCount(performance.confusion_matrix.fp)}</p>
                      <p className="text-[10px] text-red-500/75">False positive</p>
                    </div>

                    <span className="self-center text-right text-[10px] text-text-muted uppercase tracking-wider">Actual fraud</span>
                    <div className="rounded-lg bg-red-50 p-3">
                      <p className="text-lg font-bold text-red-500">{formatCount(performance.confusion_matrix.fn)}</p>
                      <p className="text-[10px] text-red-500/75">False negative</p>
                    </div>
                    <div className="rounded-lg bg-green-100 p-3">
                      <p className="text-lg font-bold text-green-700">{formatCount(performance.confusion_matrix.tp)}</p>
                      <p className="text-[10px] text-green-700/75">True positive</p>
                    </div>
                  </div>
                </>
              ) : (
                <EmptyPanel message="No confusion-matrix data is available." />
              )}
            </div>
          </article>

          <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary">ROC curve</h3>
            <p className="mt-1 text-xs text-text-muted">
              AUC: {isLoading ? 'Loading…' : formatRatio(metrics?.roc_auc)}
            </p>
            <div className="h-64 mt-3">
              {isLoading ? <LoadingBlock className="h-full" /> : rocData.length === 0 ? (
                <EmptyPanel message="The API did not return ROC-curve points." />
              ) : isMounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rocData} margin={{ top: 5, right: 12, left: -18, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="fpr"
                      type="number"
                      domain={[0, 1]}
                      tickCount={6}
                      fontSize={10}
                      stroke="#9CA3AF"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => formatRatio(value, 0)}
                      label={{ value: 'False positive rate', position: 'insideBottom', offset: -2, fontSize: 10, fill: '#9CA3AF' }}
                    />
                    <YAxis
                      type="number"
                      domain={[0, 1]}
                      tickCount={6}
                      fontSize={10}
                      stroke="#9CA3AF"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => formatRatio(value, 0)}
                      label={{ value: 'True positive rate', angle: -90, position: 'insideLeft', offset: 12, fontSize: 10, fill: '#9CA3AF' }}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      formatter={(value: number, name: string) => [
                        formatRatio(value, 2),
                        name === 'Saved model' ? 'True positive rate' : 'Random baseline',
                      ]}
                      labelFormatter={(value) => `False positive rate: ${formatRatio(value, 2)}`}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line dataKey="baseline" name="Random baseline" stroke="#9CA3AF" strokeDasharray="4 4" strokeWidth={1.5} dot={false} activeDot={false} />
                    <Line dataKey="tpr" name="Saved model" stroke="#6C63FF" strokeWidth={2.5} dot={false} activeDot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : null}
            </div>
          </article>

          <article className="bg-bg-card rounded-xl border border-border-light p-5 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary">Top important features</h3>
            <p className="mt-1 text-xs text-text-muted">
              Model-derived importance; the scale depends on the selected model.
            </p>
            <div className="h-64 mt-3">
              {isLoading ? <LoadingBlock className="h-full" /> : featureData.length === 0 ? (
                <EmptyPanel message="Feature-importance data is not available for this saved model." />
              ) : isMounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={featureData} layout="vertical" margin={{ top: 0, right: 10, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                    <XAxis
                      type="number"
                      fontSize={10}
                      stroke="#9CA3AF"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={formatImportance}
                    />
                    <YAxis
                      dataKey="feature"
                      type="category"
                      fontSize={9}
                      stroke="#9CA3AF"
                      tickLine={false}
                      axisLine={false}
                      width={110}
                    />
                    <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [formatImportance(value), 'Importance']} />
                    <Bar dataKey="importance" name="Importance" fill="#6C63FF" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : null}
            </div>
          </article>
        </section>
      </div>
    </AppShell>
  );
}
