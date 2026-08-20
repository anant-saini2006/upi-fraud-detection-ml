'use client';

import {
  ChangeEvent,
  DragEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import AppShell from '@/components/AppShell';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  analyseCSV,
  api,
  type AmountDistribution,
  type CsvAnalysis,
  type DatasetInfo,
  type FraudByTypeRow,
  type Stats,
} from '@/lib/api';

type AnalysisData = {
  stats: Stats | null;
  fraudByType: FraudByTypeRow[] | null;
  amountDistribution: AmountDistribution | null;
  datasetInfo: DatasetInfo | null;
};

type AnalysisFailures = Record<keyof AnalysisData, boolean>;

const tooltipStyle = {
  border: '1px solid #E5E7EB',
  borderRadius: 8,
  boxShadow: '0 8px 20px rgba(15, 23, 42, 0.10)',
  fontSize: 12,
};

function emptyAnalysisData(): AnalysisData {
  return {
    stats: null,
    fraudByType: null,
    amountDistribution: null,
    datasetInfo: null,
  };
}

function noFailures(): AnalysisFailures {
  return {
    stats: false,
    fraudByType: false,
    amountDistribution: false,
    datasetInfo: false,
  };
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatNumber(value: unknown): string {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
}

function formatAmount(value: unknown): string {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value: unknown): string {
  if (!isFiniteNumber(value)) return '—';
  return `${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value)}%`;
}

function LoadingBlock({ className = '' }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-xl bg-gray-100 ${className}`}
      aria-label="Loading dataset analysis"
    />
  );
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-8 text-center">
      <span className="material-symbols-outlined text-3xl text-text-muted mb-2">data_usage</span>
      <p className="text-xs text-text-muted leading-relaxed">{message}</p>
    </div>
  );
}

function UnavailableChart({ label }: { label: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-8 text-center">
      <span className="material-symbols-outlined text-3xl text-amber-500 mb-2">cloud_off</span>
      <p className="text-xs text-text-muted leading-relaxed">
        {label} could not be loaded. Refresh the page to try again.
      </p>
    </div>
  );
}

function sourceTitle(source: string | undefined): string {
  const normalized = source?.toLowerCase() ?? '';
  if (/synthetic|fixture|generated|mock/.test(normalized)) return 'Synthetic local fixture';
  if (normalized.includes('public')) return 'Public digital-payments dataset';
  return source ? 'Dataset provenance' : 'Dataset provenance unavailable';
}

export default function DatasetAnalysis() {
  const [analysis, setAnalysis] = useState<AnalysisData>(emptyAnalysisData);
  const [failures, setFailures] = useState<AnalysisFailures>(noFailures);
  const [isLoading, setIsLoading] = useState(true);
  const [isMounted, setIsMounted] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [uploadedAnalysis, setUploadedAnalysis] = useState<CsvAnalysis | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadAnalysis() {
      setIsLoading(true);
      setAnalysis(emptyAnalysisData());
      setFailures(noFailures());

      const [stats, fraudByType, amountDistribution, datasetInfo] = await Promise.allSettled([
        api.stats(),
        api.fraudByType(),
        api.amountDistribution(),
        api.datasetInfo(),
      ] as const);

      if (cancelled) return;

      setAnalysis({
        stats: stats.status === 'fulfilled' ? stats.value : null,
        fraudByType: fraudByType.status === 'fulfilled' ? fraudByType.value : null,
        amountDistribution: amountDistribution.status === 'fulfilled' ? amountDistribution.value : null,
        datasetInfo: datasetInfo.status === 'fulfilled' ? datasetInfo.value : null,
      });
      setFailures({
        stats: stats.status === 'rejected',
        fraudByType: fraudByType.status === 'rejected',
        amountDistribution: amountDistribution.status === 'rejected',
        datasetInfo: datasetInfo.status === 'rejected',
      });
      setIsLoading(false);
    }

    void loadAnalysis();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const typeChartData = useMemo(() => {
    return (analysis.fraudByType ?? [])
      .filter((row) => isFiniteNumber(row.total) && isFiniteNumber(row.fraud))
      .map((row) => ({
        type: row.type,
        legitimate: Math.max(0, row.total - row.fraud),
        fraud: row.fraud,
        fraudRate: row.fraud_rate,
        total: row.total,
      }))
      .sort((left, right) => right.total - left.total);
  }, [analysis.fraudByType]);

  const amountChartData = useMemo(() => {
    const distribution = analysis.amountDistribution;
    if (!distribution) return [];

    return [
      {
        metric: 'Minimum',
        legitimate: distribution.legitimate.min,
        fraud: distribution.fraud.min,
      },
      {
        metric: '25th percentile',
        legitimate: distribution.legitimate.q1,
        fraud: distribution.fraud.q1,
      },
      {
        metric: 'Median',
        legitimate: distribution.legitimate.median,
        fraud: distribution.fraud.median,
      },
      {
        metric: '75th percentile',
        legitimate: distribution.legitimate.q3,
        fraud: distribution.fraud.q3,
      },
      {
        metric: 'Mean',
        legitimate: distribution.legitimate.mean,
        fraud: distribution.fraud.mean,
      },
    ].filter((row) => isFiniteNumber(row.legitimate) || isFiniteNumber(row.fraud));
  }, [analysis.amountDistribution]);

  const uploadedTypeData = useMemo(() => {
    return (uploadedAnalysis?.by_type ?? [])
      .filter((row) => isFiniteNumber(row.total) && isFiniteNumber(row.fraud))
      .map((row) => ({
        type: row.type,
        legitimate: Math.max(0, row.total - row.fraud),
        fraud: row.fraud,
        total: row.total,
      }))
      .sort((left, right) => right.total - left.total);
  }, [uploadedAnalysis]);

  const source = analysis.datasetInfo?.provenance.source || analysis.stats?.dataset_source;
  const isSyntheticSource = /synthetic|fixture|generated|mock/.test(source?.toLowerCase() ?? '');
  const networkDisclosure = analysis.datasetInfo?.provenance.real_upi_network_data === true
    ? 'The API marks this source as real UPI-network data; verify that provenance before presenting results.'
    : 'It is not connected to NPCI, a bank, or the live UPI network.';
  const hasAnyFailure = Object.values(failures).some(Boolean);
  const hasAnyData = Object.values(analysis).some((value) => value !== null);
  const totalRows = analysis.datasetInfo?.rows ?? analysis.stats?.total_transactions;

  const datasetSummary = [
    { label: 'Rows', value: formatNumber(totalRows) },
    { label: 'Columns', value: analysis.datasetInfo ? formatNumber(analysis.datasetInfo.columns.length) : '—' },
    { label: 'Target column', value: analysis.datasetInfo?.target_column ?? '—' },
    { label: 'Fraud-labelled records', value: formatNumber(analysis.stats?.fraud_count) },
    { label: 'Fraud rate', value: formatPercent(analysis.stats?.fraud_rate) },
    { label: 'Average amount', value: formatAmount(analysis.stats?.avg_amount) },
  ];

  async function analyseUploadedFile(file: File | undefined) {
    if (!file) return;

    setUploadedFileName(file.name);
    setUploadedAnalysis(null);
    setUploadError(null);

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadError('Please choose a CSV file.');
      return;
    }

    setIsUploading(true);
    try {
      const result = await analyseCSV(file);
      setUploadedAnalysis(result);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'The CSV could not be analysed.');
    } finally {
      setIsUploading(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    void analyseUploadedFile(file);
    event.target.value = '';
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    void analyseUploadedFile(event.dataTransfer.files?.[0]);
  }

  if (!isLoading && !hasAnyData && hasAnyFailure) {
    return (
      <AppShell>
        <div className="min-h-[60vh] flex items-center justify-center">
          <div className="max-w-md bg-bg-card border border-border-light rounded-xl p-8 shadow-card text-center">
            <span className="material-symbols-outlined text-4xl text-amber-500 mb-3">cloud_off</span>
            <h3 className="text-lg font-semibold text-text-primary">Dataset analysis is unavailable</h3>
            <p className="mt-2 text-sm text-text-secondary leading-relaxed">
              The inference API could not be reached. Confirm that it is running and that
              <code className="mx-1 text-xs bg-gray-100 px-1.5 py-0.5 rounded">NEXT_PUBLIC_API_URL</code>
              is configured correctly.
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
        <section className="bg-primary/5 border border-primary/15 rounded-xl p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            {sourceTitle(source)}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-text-primary">Dataset-backed exploratory analysis</h3>
          <p className="mt-1 max-w-4xl text-sm text-text-secondary leading-relaxed">
            {source
              ? <>Source reported by the API: <strong className="font-medium text-text-primary">{source}</strong>. </>
              : 'The API has not returned dataset provenance yet. '}
            {isSyntheticSource
              ? 'This local dataset is synthetic and is used only as a development fixture. '
              : ''}
            {networkDisclosure}
          </p>
          {analysis.datasetInfo?.provenance.validation_note && (
            <p className="mt-2 text-xs text-text-muted leading-relaxed">
              Validation note: {analysis.datasetInfo.provenance.validation_note}
            </p>
          )}
        </section>

        {hasAnyFailure && hasAnyData && (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined text-amber-600 text-lg mt-0.5">warning</span>
              <p className="text-sm text-amber-900">
                Some analysis sections are unavailable. Any visible figures still come directly from the API.
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

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <section className="bg-bg-card rounded-xl border border-border-light p-6 shadow-card">
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Upload a CSV for quick analysis</h3>
                <p className="mt-1 text-xs text-text-muted">
                  The uploaded file is analysed separately; it does not retrain or replace the saved model.
                </p>
              </div>
              <span className="material-symbols-outlined text-primary">upload_file</span>
            </div>

            <div
              className="border-2 border-dashed border-border-light rounded-xl p-7 text-center transition-colors hover:border-primary/40"
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
            >
              <span className="material-symbols-outlined text-4xl text-text-muted mb-3 block">upload_file</span>
              <p className="text-sm text-text-secondary">
                {uploadedFileName ?? 'Drag a CSV here, or choose a file'}
              </p>
              <input
                ref={uploadInputRef}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                onChange={handleFileChange}
              />
              <button
                type="button"
                onClick={() => uploadInputRef.current?.click()}
                disabled={isUploading}
                className="mt-3 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60 transition-colors shadow-sm"
              >
                {isUploading ? 'Analysing…' : 'Browse file'}
              </button>
              <p className="text-[10px] text-text-muted mt-3">CSV only · Maximum file size: 20 MB</p>
            </div>

            <div className="min-h-6 mt-3" aria-live="polite">
              {uploadError && (
                <p className="flex items-start gap-1.5 text-xs text-danger">
                  <span className="material-symbols-outlined text-sm">error</span>
                  {uploadError}
                </p>
              )}
              {isUploading && <p className="text-xs text-text-muted">Reading and profiling the uploaded CSV…</p>}
            </div>
          </section>

          <section className="bg-bg-card rounded-xl border border-border-light p-6 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary mb-4">Current dataset summary</h3>
            {isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 6 }, (_, index) => <LoadingBlock key={index} className="h-7" />)}
              </div>
            ) : failures.stats && failures.datasetInfo ? (
              <div className="h-52"><UnavailableChart label="Dataset summary" /></div>
            ) : (
              <div className="space-y-2">
                {datasetSummary.map((item) => (
                  <div key={item.label} className="flex items-center justify-between gap-4 py-2 border-b border-border-light last:border-0">
                    <span className="text-xs text-text-secondary">{item.label}</span>
                    <span className="text-right text-sm font-semibold text-text-primary break-all">{item.value}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {uploadedAnalysis && (
          <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
            <div className="px-5 py-4 border-b border-border-light flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Uploaded CSV analysis</h3>
                <p className="mt-1 text-xs text-text-muted">{uploadedFileName}</p>
              </div>
              <span className="inline-flex w-fit items-center gap-1.5 px-2.5 py-1 bg-green-50 text-green-700 rounded-full text-xs font-medium">
                <span className="material-symbols-outlined text-sm">check_circle</span>
                Analysed
              </span>
            </div>
            <div className="p-5 grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-text-muted">Rows</p>
                <p className="mt-1 text-lg font-semibold text-text-primary">{formatNumber(uploadedAnalysis.rows)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-text-muted">Columns</p>
                <p className="mt-1 text-lg font-semibold text-text-primary">{formatNumber(uploadedAnalysis.columns.length)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-text-muted">Missing values</p>
                <p className="mt-1 text-lg font-semibold text-text-primary">{formatNumber(uploadedAnalysis.missing)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-text-muted">Fraud rate</p>
                <p className="mt-1 text-lg font-semibold text-text-primary">
                  {uploadedAnalysis.fraud_rate === undefined ? 'No isFraud column' : formatPercent(uploadedAnalysis.fraud_rate)}
                </p>
              </div>
            </div>

            <div className="px-5 pb-5 grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="rounded-xl bg-gray-50 p-4">
                <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Detected columns</p>
                <p className="mt-2 text-xs text-text-muted leading-relaxed break-words">
                  {uploadedAnalysis.columns.length > 0 ? uploadedAnalysis.columns.join(', ') : 'No columns detected.'}
                </p>
              </div>
              {uploadedAnalysis.amount_stats && (
                <div className="rounded-xl bg-gray-50 p-4">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Amount summary</p>
                  <div className="mt-2 grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <p className="text-text-muted">Legitimate mean / median</p>
                      <p className="mt-1 font-semibold text-text-primary">
                        {formatAmount(uploadedAnalysis.amount_stats.legit.mean)} / {formatAmount(uploadedAnalysis.amount_stats.legit.median)}
                      </p>
                    </div>
                    <div>
                      <p className="text-text-muted">Fraud mean / median</p>
                      <p className="mt-1 font-semibold text-text-primary">
                        {formatAmount(uploadedAnalysis.amount_stats.fraud.mean)} / {formatAmount(uploadedAnalysis.amount_stats.fraud.median)}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {uploadedTypeData.length > 0 && (
              <div className="px-5 pb-5">
                <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-3">
                  Uploaded file: fraud-labelled records by transaction type
                </h4>
                <div className="h-64">
                  {isMounted && (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={uploadedTypeData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                        <XAxis dataKey="type" fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} />
                        <YAxis fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} tickFormatter={formatNumber} />
                        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [formatNumber(value), 'Records']} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="legitimate" stackId="records" name="Remaining records" fill="#C4B5FD" radius={[0, 0, 0, 0]} />
                        <Bar dataKey="fraud" stackId="records" name="Fraud-labelled records" fill="#EF4444" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            )}
          </section>
        )}

        <section className="bg-bg-card rounded-xl border border-border-light shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border-light">
            <h3 className="text-sm font-semibold text-text-primary">Exploratory insights from the current dataset</h3>
            <p className="mt-1 text-xs text-text-muted">All figures below are loaded from the inference API; no placeholder values are shown.</p>
          </div>

          <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <h4 className="text-xs font-medium text-text-secondary mb-1 uppercase tracking-wider">
                Records by transaction type
              </h4>
              <p className="text-xs text-text-muted mb-3">Fraud-labelled records are shown against the remaining records.</p>
              <div className="h-72">
                {isLoading ? <LoadingBlock className="h-full" /> : failures.fraudByType ? (
                  <UnavailableChart label="Transaction-type analysis" />
                ) : typeChartData.length === 0 ? (
                  <EmptyChart message="No transaction-type records are available in this dataset." />
                ) : isMounted ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={typeChartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                      <XAxis dataKey="type" fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} />
                      <YAxis fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} tickFormatter={formatNumber} />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        formatter={(value: number, name: string) => [
                          formatNumber(value),
                          name === 'Fraud rate' ? 'Fraud rate' : name,
                        ]}
                      />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="legitimate" stackId="records" name="Remaining records" fill="#C4B5FD" />
                      <Bar dataKey="fraud" stackId="records" name="Fraud-labelled records" fill="#EF4444" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : null}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-medium text-text-secondary mb-1 uppercase tracking-wider">
                Amount distribution summary
              </h4>
              <p className="text-xs text-text-muted mb-3">
                Label-separated amounts. The API clips the display at its 99th-percentile cap to keep outliers readable.
              </p>
              <div className="h-72">
                {isLoading ? <LoadingBlock className="h-full" /> : failures.amountDistribution ? (
                  <UnavailableChart label="Amount distribution" />
                ) : amountChartData.length === 0 ? (
                  <EmptyChart message="No amount distribution is available in this dataset." />
                ) : isMounted ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={amountChartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                      <XAxis dataKey="metric" fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} />
                      <YAxis fontSize={10} stroke="#9CA3AF" tickLine={false} axisLine={false} tickFormatter={(value) => formatAmount(value)} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [formatAmount(value), 'Amount']} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="legitimate" name="Legitimate" fill="#6C63FF" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="fraud" name="Fraud-labelled" fill="#EF4444" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : null}
              </div>
              {!isLoading && analysis.amountDistribution && !failures.amountDistribution && (
                <p className="mt-2 text-[10px] text-text-muted">
                  Display cap: {formatAmount(analysis.amountDistribution.display_cap)}
                </p>
              )}
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
