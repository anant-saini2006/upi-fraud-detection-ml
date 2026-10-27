'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Password validation indicators
  const hasMinLength = password.length >= 8;
  const hasLetter = /[a-zA-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (fullName.trim().length < 2) {
      setError('Please provide your full name (at least 2 characters).');
      return;
    }

    const emailRegex = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
    if (!emailRegex.test(email.trim())) {
      setError('Please provide a valid email address (e.g. name@example.com).');
      return;
    }

    if (!hasMinLength) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (!hasLetter || !hasNumber) {
      setError('Password must contain both letters and numbers.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match. Please re-enter your confirmation password.');
      return;
    }

    setLoading(true);

    try {
      await signup({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password,
      });
      router.push('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed. Please try again.');
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

      {/* Main Registration Card */}
      <main className="max-w-md w-full mx-auto my-auto">
        <div className="bg-bg-card rounded-2xl border border-border-light p-6 sm:p-8 shadow-card space-y-6">
          <div className="text-center space-y-1.5">
            <h1 className="text-2xl font-bold text-text-primary">Create an Account</h1>
            <p className="text-xs text-text-secondary">
              Register for personal access to the real-time UPI transaction scoring engine.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1.5">
                Full Name
              </label>
              <div className="relative">
                <span className="material-symbols-outlined text-text-muted absolute left-3 top-2.5 text-lg">
                  badge
                </span>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Alice Sharma"
                  required
                  className="w-full pl-9 pr-3.5 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1.5">
                Email Address
              </label>
              <div className="relative">
                <span className="material-symbols-outlined text-text-muted absolute left-3 top-2.5 text-lg">
                  mail
                </span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                  className="w-full pl-9 pr-3.5 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1.5">
                Password
              </label>
              <div className="relative">
                <span className="material-symbols-outlined text-text-muted absolute left-3 top-2.5 text-lg">
                  lock
                </span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
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

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1.5">
                Confirm Password
              </label>
              <div className="relative">
                <span className="material-symbols-outlined text-text-muted absolute left-3 top-2.5 text-lg">
                  lock_reset
                </span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-type your password"
                  required
                  className="w-full pl-9 pr-3.5 py-2.5 rounded-lg border border-border-light text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
                />
              </div>
            </div>

            {/* Password Requirement Badges */}
            <div className="p-3 bg-gray-50 rounded-xl border border-border-light space-y-1.5">
              <p className="text-[11px] font-semibold text-text-secondary">Password Requirements:</p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className={`flex items-center gap-1.5 ${hasMinLength ? 'text-emerald-700 font-medium' : 'text-text-muted'}`}>
                  <span className="material-symbols-outlined text-sm">
                    {hasMinLength ? 'check_circle' : 'radio_button_unchecked'}
                  </span>
                  <span>8+ characters</span>
                </div>
                <div className={`flex items-center gap-1.5 ${hasLetter && hasNumber ? 'text-emerald-700 font-medium' : 'text-text-muted'}`}>
                  <span className="material-symbols-outlined text-sm">
                    {hasLetter && hasNumber ? 'check_circle' : 'radio_button_unchecked'}
                  </span>
                  <span>Letters & numbers</span>
                </div>
                <div className={`flex items-center gap-1.5 col-span-2 ${passwordsMatch ? 'text-emerald-700 font-medium' : 'text-text-muted'}`}>
                  <span className="material-symbols-outlined text-sm">
                    {passwordsMatch ? 'check_circle' : 'radio_button_unchecked'}
                  </span>
                  <span>Passwords match</span>
                </div>
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
                  <span>Creating Account...</span>
                </>
              ) : (
                <span>Register & Continue</span>
              )}
            </button>
          </form>

          {/* Link to Login */}
          <div className="pt-4 border-t border-border-light text-center space-y-2">
            <p className="text-xs text-text-secondary">
              Already have an account?{' '}
              <Link href="/login" className="text-primary hover:underline font-semibold">
                Sign In
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
        UPI Fraud Detection ML Prototype • Zero Plaintext Password Guarantee
      </footer>
    </div>
  );
}
