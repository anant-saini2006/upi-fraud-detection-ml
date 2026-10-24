'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, setAdminToken } from '@/lib/api';

export default function AdminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('demo1234');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.adminLogin({ username, password });
      setAdminToken(res.token);
      window.location.href = '/admin';
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid credentials');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-main flex flex-col justify-between p-4 sm:p-6">
      <header className="max-w-md w-full mx-auto text-center pt-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 bg-primary/10 text-primary border border-primary/20 rounded-full text-xs font-semibold">
          <span className="material-symbols-outlined text-sm">lock</span>
          <span>Gated Operations Area</span>
        </div>
      </header>

      <main className="max-w-md w-full mx-auto my-auto">
        <div className="bg-bg-card rounded-2xl border border-border-light p-6 sm:p-8 shadow-card space-y-6">
          {/* Logo & Header */}
          <div className="text-center space-y-2">
            <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center mx-auto shadow-md shadow-primary/25">
              <span className="material-symbols-outlined text-white text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                shield
              </span>
            </div>
            <h1 className="text-xl font-bold text-text-primary">Admin Console</h1>
            <p className="text-xs text-text-muted">
              Sign in to manage risk thresholds, review queue, and ledger telemetry.
            </p>
          </div>

          {/* Demo hint */}
          <div className="bg-gray-50 border border-border-light rounded-lg p-3 text-xs text-text-secondary text-center">
            Demo Credentials: <span className="font-mono font-semibold text-text-primary">admin</span> /{' '}
            <span className="font-mono font-semibold text-text-primary">demo1234</span>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
              />
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs font-medium text-danger flex items-center gap-2">
                <span className="material-symbols-outlined text-base">error</span>
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-lg bg-primary hover:bg-primary-dark text-white font-medium text-sm shadow-sm transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Signing In...</span>
                </>
              ) : (
                <span>Sign In to Admin</span>
              )}
            </button>
          </form>

          <div className="pt-4 border-t border-border-light text-center">
            <Link href="/" className="text-xs text-text-secondary hover:text-primary transition font-medium">
              ← Return to Main Dashboard
            </Link>
          </div>
        </div>
      </main>

      <footer className="py-4 text-center text-xs text-text-muted">
        UPI Fraud Detection Prototype • Gated Admin Security Area
      </footer>
    </div>
  );
}
