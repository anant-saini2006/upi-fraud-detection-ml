'use client';

import Link from 'next/link';
import AppShell from '@/components/AppShell';
import { useAuth } from '@/lib/auth-context';

export default function ProfilePage() {
  const { user, isLoading, logout } = useAuth();

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-text-muted">Loading profile...</p>
        </div>
      </AppShell>
    );
  }

  if (!user) {
    return (
      <AppShell>
        <div className="max-w-md mx-auto text-center py-12 space-y-4">
          <div className="w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center mx-auto">
            <span className="material-symbols-outlined text-2xl">lock</span>
          </div>
          <h2 className="text-xl font-bold text-text-primary">Sign In Required</h2>
          <p className="text-xs text-text-secondary leading-relaxed">
            Please log in or create an account to view your profile and personal scoring history.
          </p>
          <div className="flex justify-center gap-3 pt-2">
            <Link
              href="/login"
              className="px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-lg text-xs font-semibold shadow-sm transition"
            >
              Sign In
            </Link>
            <Link
              href="/signup"
              className="px-4 py-2 border border-border-light bg-white hover:bg-gray-50 text-text-primary rounded-lg text-xs font-semibold transition"
            >
              Register
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header Card */}
        <div className="bg-bg-card border border-border-light rounded-2xl p-6 sm:p-8 shadow-card">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-primary to-primary-light text-white text-2xl font-bold flex items-center justify-center shadow-md shadow-primary/25">
                {user.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-text-primary">{user.full_name}</h1>
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                      user.role === 'admin'
                        ? 'bg-primary/10 text-primary border border-primary/20'
                        : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    }`}
                  >
                    {user.role === 'admin' ? 'Administrator' : 'Standard User'}
                  </span>
                </div>
                <p className="text-xs text-text-secondary mt-0.5">{user.email}</p>
                <p className="text-[10px] text-text-muted mt-1">User ID: #{user.id}</p>
              </div>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <Link
                href="/predict"
                className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 bg-primary hover:bg-primary-dark text-white text-xs font-semibold rounded-lg shadow-sm transition"
              >
                <span className="material-symbols-outlined text-base">search</span>
                <span>Score Transaction</span>
              </Link>
              <button
                onClick={logout}
                className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3 py-2 border border-border-light bg-white hover:bg-red-50 hover:text-danger text-text-secondary text-xs font-semibold rounded-lg shadow-sm transition"
              >
                <span className="material-symbols-outlined text-base">logout</span>
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>

        {/* Roles & Permissions Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* User Capabilities */}
          <div className="bg-bg-card border border-border-light rounded-xl p-5 shadow-card space-y-4">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-xl">verified_user</span>
              <h3 className="text-sm font-bold text-text-primary">Your Permitted Capabilities</h3>
            </div>
            <ul className="space-y-2.5 text-xs text-text-secondary">
              <li className="flex items-start gap-2">
                <span className="material-symbols-outlined text-emerald-500 text-base shrink-0">check_circle</span>
                <span><strong>Instant ML Scoring:</strong> Evaluate any custom UPI transaction parameters against the PaySim classification model.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="material-symbols-outlined text-emerald-500 text-base shrink-0">check_circle</span>
                <span><strong>Isolated History:</strong> Access and review your personal scored transaction history with full privacy isolation.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="material-symbols-outlined text-emerald-500 text-base shrink-0">check_circle</span>
                <span><strong>Accounting Policy:</strong> View double-entry balance validation and heuristic risk band assessments.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="material-symbols-outlined text-emerald-500 text-base shrink-0">check_circle</span>
                <span><strong>Public Insights:</strong> Explore aggregate dataset metrics and model accuracy metrics.</span>
              </li>
            </ul>
          </div>

          {/* Admin Gating Status */}
          <div className="bg-bg-card border border-border-light rounded-xl p-5 shadow-card space-y-4">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-xl">admin_panel_settings</span>
              <h3 className="text-sm font-bold text-text-primary">Admin Operations Area</h3>
            </div>
            {user.role === 'admin' ? (
              <div className="space-y-3 text-xs">
                <div className="p-3 bg-primary/5 border border-primary/15 rounded-lg text-text-primary space-y-1">
                  <p className="font-semibold text-primary">Administrator Role Active</p>
                  <p className="text-text-secondary">
                    You have elevated access to the payment stream, review queue, risk slider adjustments, and demo telemetry.
                  </p>
                </div>
                <Link
                  href="/admin"
                  className="w-full inline-flex items-center justify-center gap-2 py-2 px-3 bg-primary text-white rounded-lg font-semibold hover:bg-primary-dark transition text-xs shadow-sm"
                >
                  <span className="material-symbols-outlined text-base">dashboard_customize</span>
                  <span>Open Admin Console</span>
                </Link>
              </div>
            ) : (
              <div className="space-y-3 text-xs text-text-secondary">
                <div className="p-3 bg-gray-50 border border-border-light rounded-lg space-y-1">
                  <p className="font-semibold text-text-primary flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-amber-500 text-base">lock</span>
                    <span>Admin Area Gated</span>
                  </p>
                  <p className="text-text-muted">
                    Administrative endpoints (`/admin`, `/api/admin/*`) require server-side administrator credentials and are forbidden for standard user accounts.
                  </p>
                </div>
                <p className="text-[11px] text-text-muted">
                  Need admin rights for testing? You can sign in with username <code className="bg-gray-100 px-1 py-0.5 rounded text-text-primary">admin</code> and password <code className="bg-gray-100 px-1 py-0.5 rounded text-text-primary">demo1234</code>.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
