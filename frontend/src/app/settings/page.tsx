'use client';

import Link from 'next/link';
import AppShell from '@/components/AppShell';
import { useAuth } from '@/lib/auth-context';

export default function SettingsPage() {
  const { user, token, isLoading, logout } = useAuth();

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-text-muted">Loading settings...</p>
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
            Please log in to manage your account and security settings.
          </p>
          <div className="flex justify-center gap-3 pt-2">
            <Link
              href="/login"
              className="px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-lg text-xs font-semibold shadow-sm transition"
            >
              Sign In
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Account Settings</h1>
          <p className="text-xs text-text-secondary">
            Manage your session security, password architecture, and preferences.
          </p>
        </div>

        {/* Security Overview Card */}
        <div className="bg-bg-card border border-border-light rounded-xl p-6 shadow-card space-y-6">
          <div className="flex items-center gap-3 pb-4 border-b border-border-light">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-xl">security</span>
            </div>
            <div>
              <h2 className="text-sm font-bold text-text-primary">Security Architecture</h2>
              <p className="text-xs text-text-secondary">Enterprise-grade encryption and token safeguards.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-gray-50 border border-border-light space-y-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-emerald-600 text-lg">enhanced_encryption</span>
                <h3 className="text-xs font-bold text-text-primary">Password Storage</h3>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                Passwords are hashed using <strong>PBKDF2-HMAC-SHA256</strong> with 200,000 iterations and 128-bit cryptographically secure random salt. Plaintext passwords are never stored or logged.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-gray-50 border border-border-light space-y-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-emerald-600 text-lg">token</span>
                <h3 className="text-xs font-bold text-text-primary">Session Security</h3>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                Sessions are backed by cryptographically signed HMAC-SHA256 stateless tokens with 7-day expiration, protected against tampering across serverless container instances.
              </p>
            </div>
          </div>

          {/* Active Session Token Inspection */}
          <div className="pt-4 border-t border-border-light space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-text-primary">Active Session Token</span>
              <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-medium border border-emerald-200">
                Verified Active
              </span>
            </div>
            <div className="p-3 bg-gray-900 rounded-lg text-emerald-400 font-mono text-xs overflow-x-auto break-all select-all">
              {token ? `${token.slice(0, 32)}...${token.slice(-16)}` : 'No token found'}
            </div>
          </div>
        </div>

        {/* Account Details Card */}
        <div className="bg-bg-card border border-border-light rounded-xl p-6 shadow-card space-y-4">
          <h2 className="text-sm font-bold text-text-primary">Account Details</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-text-muted block">Full Name</span>
              <span className="font-semibold text-text-primary text-sm mt-0.5 block">{user.full_name}</span>
            </div>

            <div>
              <span className="text-text-muted block">Email Address</span>
              <span className="font-semibold text-text-primary text-sm mt-0.5 block">{user.email}</span>
            </div>

            <div>
              <span className="text-text-muted block">Assigned Role</span>
              <span className="font-semibold text-text-primary text-sm mt-0.5 block capitalize">{user.role}</span>
            </div>

            <div>
              <span className="text-text-muted block">User ID</span>
              <span className="font-semibold text-text-primary text-sm mt-0.5 block">#{user.id}</span>
            </div>
          </div>

          <div className="pt-4 border-t border-border-light flex justify-end">
            <button
              onClick={logout}
              className="inline-flex items-center gap-2 px-4 py-2 bg-red-50 hover:bg-red-100 text-danger border border-red-200 rounded-lg text-xs font-semibold transition"
            >
              <span className="material-symbols-outlined text-base">logout</span>
              <span>Terminate Session (Sign Out)</span>
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
