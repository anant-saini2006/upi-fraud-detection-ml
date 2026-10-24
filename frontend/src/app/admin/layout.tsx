'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import AppShell from '@/components/AppShell';
import { api, clearAdminToken, getAdminToken } from '@/lib/api';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const [reviewCount, setReviewCount] = useState<number>(0);
  const [simulating, setSimulating] = useState<boolean>(false);
  const [resetting, setResetting] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const isLoginPage = pathname === '/admin/login';
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);

  // Auth gate check
  useEffect(() => {
    if (isLoginPage) {
      setIsCheckingAuth(false);
      return;
    }
    const token = getAdminToken();
    if (!token) {
      setIsAuthenticated(false);
      setIsCheckingAuth(false);
      window.location.href = '/admin/login';
    } else {
      setIsAuthenticated(true);
      setIsCheckingAuth(false);
    }
  }, [pathname, isLoginPage]);

  // Review count poller
  useEffect(() => {
    if (isLoginPage || !isAuthenticated) return;
    const fetchCount = () => {
      api
        .adminReviewCount()
        .then((res) => setReviewCount(res.count))
        .catch(() => {});
    };

    fetchCount();
    const interval = setInterval(fetchCount, 5000);
    return () => clearInterval(interval);
  }, [isLoginPage, isAuthenticated]);

  const handleSimulate = async () => {
    setSimulating(true);
    setActionMessage(null);
    try {
      const res = await api.adminSimulate(50);
      setActionMessage({
        text: `Simulated 50 payments! Succeeded: ${res.results.succeeded || 0}, Reviews: ${res.results.requires_review || 0}, Blocked: ${res.results.blocked || 0}`,
        type: 'success',
      });
      window.dispatchEvent(new Event('payments-updated'));
    } catch (err: unknown) {
      setActionMessage({
        text: err instanceof Error ? err.message : 'Simulation failed',
        type: 'error',
      });
    } finally {
      setSimulating(false);
      setTimeout(() => setActionMessage(null), 6000);
    }
  };

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset all demo payments and restore wallet balances?')) {
      return;
    }
    setResetting(true);
    setActionMessage(null);
    try {
      const res = await api.adminReset();
      setActionMessage({ text: res.message || 'Demo data reset successfully!', type: 'success' });
      setReviewCount(0);
      window.dispatchEvent(new Event('payments-updated'));
    } catch (err: unknown) {
      setActionMessage({
        text: err instanceof Error ? err.message : 'Reset failed',
        type: 'error',
      });
    } finally {
      setResetting(false);
      setTimeout(() => setActionMessage(null), 6000);
    }
  };

  const handleLogout = () => {
    clearAdminToken();
    window.location.href = '/admin/login';
  };

  if (isLoginPage) {
    return <>{children}</>;
  }

  if (isCheckingAuth || !isAuthenticated) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-text-muted">Verifying administrator session...</p>
        </div>
      </AppShell>
    );
  }

  const navLinks = [
    { label: 'Live Feed', href: '/admin', icon: 'stream' },
    {
      label: 'Review Queue',
      href: '/admin/reviews',
      icon: 'rate_review',
      badge: reviewCount,
    },
    { label: 'Risk Settings', href: '/admin/settings', icon: 'tune' },
  ];

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Admin Navigation Bar with Action Controls */}
        <div className="bg-bg-card border border-border-light rounded-xl p-3 sm:p-4 shadow-card flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          {/* Subnav Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    isActive
                      ? 'bg-primary text-white shadow-sm'
                      : 'text-text-secondary hover:bg-gray-100 hover:text-text-primary'
                  }`}
                >
                  <span className="material-symbols-outlined text-lg" style={isActive ? { fontVariationSettings: "'FILL' 1" } : {}}>
                    {link.icon}
                  </span>
                  <span>{link.label}</span>
                  {link.badge !== undefined && link.badge > 0 && (
                    <span
                      className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold leading-none ${
                        isActive ? 'bg-white text-primary' : 'bg-danger text-white'
                      }`}
                    >
                      {link.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>

          {/* Quick Action Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleSimulate}
              disabled={simulating || resetting}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-primary hover:bg-primary-dark text-white text-xs font-semibold rounded-lg shadow-sm transition disabled:opacity-50"
            >
              {simulating ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Simulating...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-base">bolt</span>
                  <span>Simulate 50</span>
                </>
              )}
            </button>

            <button
              onClick={handleReset}
              disabled={simulating || resetting}
              className="inline-flex items-center gap-1.5 px-3 py-2 border border-border-light bg-white hover:bg-gray-50 text-text-primary text-xs font-semibold rounded-lg shadow-sm transition disabled:opacity-50"
            >
              {resetting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-text-muted border-t-transparent rounded-full animate-spin" />
                  <span>Resetting...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-base">restart_alt</span>
                  <span>Reset Demo</span>
                </>
              )}
            </button>

            <button
              onClick={handleLogout}
              className="p-2 text-text-muted hover:text-danger hover:bg-red-50 rounded-lg transition"
              title="Sign Out"
            >
              <span className="material-symbols-outlined text-lg">logout</span>
            </button>
          </div>
        </div>

        {/* Action Message Alert */}
        {actionMessage && (
          <div
            className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm font-medium ${
              actionMessage.type === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-red-50 border-red-200 text-red-800'
            }`}
          >
            <span className="material-symbols-outlined text-lg">
              {actionMessage.type === 'success' ? 'check_circle' : 'error'}
            </span>
            <span>{actionMessage.text}</span>
          </div>
        )}

        {/* Content */}
        <div>{children}</div>
      </div>
    </AppShell>
  );
}
