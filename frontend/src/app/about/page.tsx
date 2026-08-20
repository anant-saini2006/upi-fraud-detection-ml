'use client';

import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import { api, type DatasetInfo } from '@/lib/api';

function LoadingSource() {
  return <span className="inline-block h-4 w-52 animate-pulse rounded bg-gray-200 align-middle" />;
}

export default function About() {
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.datasetInfo()
      .then((value) => {
        if (!cancelled) setDataset(value);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6">
        <section className="bg-primary/5 border border-primary/15 rounded-xl p-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">B.Tech final-year capstone</p>
          <h3 className="mt-1 text-2xl font-semibold text-text-primary">UPI-style fraud detection using machine learning</h3>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-text-secondary">
            This application classifies digital-payment records as likely legitimate or potentially fraudulent using a
            saved machine-learning model. It is a prototype for UPI-style use cases, not a connection to the live UPI
            network or a real-time payment-monitoring system.
          </p>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="bg-bg-card rounded-xl border border-border-light p-6 shadow-card">
            <h4 className="text-base font-semibold text-text-primary">Dataset and validation</h4>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex flex-col gap-1 border-b border-border-light pb-3">
                <dt className="text-text-secondary">Current dataset source</dt>
                <dd className="font-medium text-text-primary">
                  {dataset ? dataset.provenance.source : error ? 'The API could not load dataset provenance.' : <LoadingSource />}
                </dd>
              </div>
              <div className="flex items-center justify-between border-b border-border-light pb-3">
                <dt className="text-text-secondary">Records available</dt>
                <dd className="font-semibold text-text-primary">{dataset ? new Intl.NumberFormat('en-IN').format(dataset.rows) : '—'}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-text-secondary">Live UPI / NPCI integration</dt>
                <dd className="font-semibold text-red-600">No</dd>
              </div>
            </dl>
            {dataset?.provenance.validation_note && (
              <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-900">
                {dataset.provenance.validation_note}
              </p>
            )}
          </section>

          <section className="bg-bg-card rounded-xl border border-border-light p-6 shadow-card">
            <h4 className="text-base font-semibold text-text-primary">How a prediction works</h4>
            <ol className="mt-4 space-y-4 text-sm text-text-secondary">
              <li className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">1</span><span>Enter transaction amount, type, hour, and the available balance fields.</span></li>
              <li className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">2</span><span>The API applies the exact saved feature-engineering and preprocessing pipeline used during training.</span></li>
              <li className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">3</span><span>The model returns a probability, prediction label, and low/medium/high risk band. No model is retrained during this request.</span></li>
            </ol>
          </section>

          <section className="bg-bg-card rounded-xl border border-border-light p-6 shadow-card">
            <h4 className="text-base font-semibold text-text-primary">Technology stack</h4>
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              {[
                ['Model', 'Python, Pandas, scikit-learn, imbalanced-learn'],
                ['API', 'FastAPI and Uvicorn'],
                ['Frontend', 'Next.js, TypeScript, Tailwind CSS, Recharts'],
                ['Persistence', 'PostgreSQL / Neon when DATABASE_URL is configured'],
              ].map(([label, detail]) => (
                <div key={label} className="rounded-lg border border-border-light bg-gray-50 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-primary">{label}</p>
                  <p className="mt-1 leading-relaxed text-text-secondary">{detail}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="bg-bg-card rounded-xl border border-border-light p-6 shadow-card">
            <h4 className="text-base font-semibold text-text-primary">Academic scope</h4>
            <ul className="mt-4 space-y-3 text-sm leading-relaxed text-text-secondary">
              <li className="flex gap-2"><span className="material-symbols-outlined text-primary text-lg">check_circle</span><span>Metrics include precision, recall, F1, and ROC-AUC; accuracy is not used as the headline measure on imbalanced data.</span></li>
              <li className="flex gap-2"><span className="material-symbols-outlined text-primary text-lg">check_circle</span><span>SMOTE is applied only to the training partition, never to the held-out test partition.</span></li>
              <li className="flex gap-2"><span className="material-symbols-outlined text-primary text-lg">check_circle</span><span>Future work could include validated public data at larger scale, streaming integration, and graph-based account-network analysis.</span></li>
            </ul>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
