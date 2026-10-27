'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectPath = searchParams.get('redirect') || '/';

  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleQuickFill = (demoEmail: string, demoPass: string) => {
    setEmail(demoEmail);
    setPassword(demoPass);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError('Please enter both your email and password.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const user = await login({ email: email.trim(), password });
      if (redirectPath && redirectPath !== '/') {
        router.push(redirectPath);
      } else if (user.role === 'admin') {
        router.push('/admin');
      } else {
        router.push('/');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid credentials. Please verify your email and password.');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-main flex flex-col justify-between p-4 sm:p-6">
      {/* Top Banner */}
      <header className="max-w-md w-full mx-auto text-center pt-6">
        <Link href="/" className="inline-flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center shadow-md shadow-primary/25 transition-transform group-hover:scale-105">
            <span className="material-symbols-outlined text-white text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
              shield
            </span>
          </div>
          <div className="text-left">
            <span className="font-bold text-text-primary text-base leading-tight block">UPI Fraud</span>
            <span className="text-[10px] text-text-muted leading-tight block">Detection System</span>
          </div>
        </Link>
      </header>

      {/* Main Login Card */}
      <main className="max-w-md w-full mx-auto my-auto">
        <div className="bg-bg-card rounded-2xl border border-border-light p-6 sm:p-8 shadow-card space-y-6">
          <div className="text-center space-y-1.5">
            <h1 className="text-2xl font-bold text-text-primary">Welcome Back</h1>
            <p className="text-xs text-text-secondary">
              Sign in to your account to access transaction scoring and fraud intelligence.
            </p>
          </div>

          {/* Demo Credentials Quick Pick */}
          <div className="bg-gray-50 border border-border-light rounded-xl p-3.5 space-y-2">
            <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider text-center">
              Quick Test Credentials
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleQuickFill('user@example.com', 'user1234')}
                className="py-1.5 px-2 bg-white hover:bg-gray-100 border border-border-light rounded-lg text-xs font-medium text-text-primary text-center transition shadow-xs"
              >
                <div className="font-semibold text-primary">Demo User</div>
                <div className="text-[10px] text-text-muted">user1234</div>
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('admin', 'demo1234')}
                className="py-1.5 px-2 bg-white hover:bg-gray-100 border border-border-light rounded-lg text-xs font-medium text-text-primary text-center transition shadow-xs"
              >
                <div className="font-semibold text-primary">Administrator</div>
                <div className="text-[10px] text-text-muted">demo1234</div>
              </button>
            </div>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1.5">
                Email or Username
              </label>
              <div className="relative">
                <span className="material-symbols-outlined text-text-muted absolute left-3 top-2.5 text-lg">
                  mail
                </span>
                <input
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                  className="w-full pl-9 pr-3.5 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold text-text-primary">Password</label>
              </div>
              <div className="relative">
                <span className="material-symbols-outlined text-text-muted absolute left-3 top-2.5 text-lg">
                  lock
                </span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  className="w-full pl-9 pr-10 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-text-muted hover:text-text-primary focus:outline-none"
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  <span className="material-symbols-outlined text-lg">
                    {showPassword ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              </div>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs font-medium text-danger flex items-start gap-2 animate-in fade-in">
                <span className="material-symbols-outlined text-base shrink-0 mt-0.5">error</span>
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-lg bg-primary hover:bg-primary-dark text-white font-medium text-sm shadow-md shadow-primary/25 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Signing In...</span>
                </>
              ) : (
                <span>Sign In</span>
              )}
            </button>
          </form>

          {/* Link to Signup */}
          <div className="pt-4 border-t border-border-light text-center space-y-2">
            <p className="text-xs text-text-secondary">
              Don&apos;t have an account?{' '}
              <Link href="/signup" className="text-primary hover:underline font-semibold">
                Sign Up
              </Link>
            </p>
            <div>
              <Link href="/" className="text-xs text-text-muted hover:text-text-primary transition font-medium inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">arrow_back</span>
                <span>Return to Dashboard</span>
              </Link>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-text-muted">
        UPI Fraud Detection ML Prototype • Secure User Authentication
      </footer>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-bg-main flex items-center justify-center"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
      <LoginForm />
    </Suspense>
  );
}
