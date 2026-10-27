'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

const navItems = [
  { href: '/', icon: 'dashboard', label: 'Dashboard' },
  { href: '/predict', icon: 'shield', label: 'Transaction Prediction' },
  { href: '/analysis', icon: 'bar_chart', label: 'Dataset Analysis' },
  { href: '/performance', icon: 'speed', label: 'Model Performance' },
  { href: '/about', icon: 'info', label: 'About' },
];

const gatewayNavItems = [
  { href: '/shop', icon: 'storefront', label: 'Demo Store' },
  { href: '/admin', icon: 'admin_panel_settings', label: 'Admin Console', adminOnly: true },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, isLoading: isAuthLoading, logout } = useAuth();
  const [reviewCount, setReviewCount] = useState(0);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Poll review count for administrators
  useEffect(() => {
    if (user?.role !== 'admin') {
      setReviewCount(0);
      return;
    }
    const fetchReviewCount = () => {
      api.adminReviewCount().then(r => setReviewCount(r.count)).catch(() => {});
    };
    fetchReviewCount();
    const interval = setInterval(fetchReviewCount, 5000);
    return () => clearInterval(interval);
  }, [user?.role]);

  // Click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsProfileOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Filter gateway items based on permissions
  const visibleGatewayItems = gatewayNavItems.filter(
    item => !item.adminOnly || user?.role === 'admin'
  );

  return (
    <div className="min-h-screen flex bg-bg-main">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-64 bg-bg-card border-r border-border-light shadow-sidebar fixed top-0 left-0 h-full z-40">
        {/* Logo */}
        <div className="p-5 border-b border-border-light">
          <Link href="/" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center shadow-md shadow-primary/20">
              <span className="material-symbols-outlined text-white text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>shield</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary leading-tight">UPI Fraud</h1>
              <p className="text-xs text-text-muted leading-tight">Detection</p>
            </div>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 overflow-y-auto">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={`flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
                      ${isActive
                        ? 'bg-primary text-white shadow-md shadow-primary/25'
                        : 'text-text-secondary hover:bg-gray-100 hover:text-text-primary'
                      }`}
                  >
                    <span
                      className="material-symbols-outlined text-xl"
                      style={isActive ? { fontVariationSettings: "'FILL' 1" } : {}}
                    >
                      {item.icon}
                    </span>
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          {/* Gateway section */}
          {visibleGatewayItems.length > 0 && (
            <div className="mt-5 pt-4 border-t border-border-light">
              <p className="px-4 pb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Payment Gateway</p>
              <ul className="space-y-1">
                {visibleGatewayItems.map((item) => {
                  const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={`flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
                          ${isActive
                            ? 'bg-primary text-white shadow-md shadow-primary/25'
                            : 'text-text-secondary hover:bg-gray-100 hover:text-text-primary'
                          }`}
                      >
                        <span
                          className="material-symbols-outlined text-xl"
                          style={isActive ? { fontVariationSettings: "'FILL' 1" } : {}}
                        >
                          {item.icon}
                        </span>
                        {item.label}
                        {item.href === '/admin' && reviewCount > 0 && (
                          <span className="ml-auto px-1.5 py-0.5 rounded-full bg-danger text-white text-[10px] font-bold leading-none">
                            {reviewCount}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </nav>

        {/* Footer badge */}
        <div className="p-4 border-t border-border-light">
          <div className="flex items-center gap-2.5 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-lg">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <div>
              <p className="text-xs font-semibold text-emerald-800">System Online</p>
              <p className="text-[10px] text-emerald-600 leading-tight">Fraud Engine Active</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex-1 md:ml-64 flex flex-col min-h-screen">
        {/* Top bar */}
        <header className="bg-bg-card border-b border-border-light px-6 py-3 flex items-center justify-between sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-text-primary capitalize">
              {[...navItems, ...gatewayNavItems].find(n => n.href === pathname)?.label || 'Dashboard'}
            </h2>
          </div>

          <div className="flex items-center gap-2">
            {/* Quick action buttons */}
            {user?.role === 'admin' && (
              <Link
                href="/admin/reviews"
                className="p-2 text-text-secondary hover:text-text-primary hover:bg-gray-100 rounded-lg transition-colors relative"
                title="Review Queue"
              >
                <span className="material-symbols-outlined text-xl">notifications</span>
                {reviewCount > 0 && (
                  <span className="absolute top-1 right-1 min-w-[16px] h-4 flex items-center justify-center px-1 rounded-full bg-danger text-white text-[10px] font-bold leading-none">
                    {reviewCount}
                  </span>
                )}
              </Link>
            )}

            {/* Profile Menu Area */}
            {isAuthLoading ? (
              <div className="flex items-center gap-2 ml-2 pl-3 border-l border-border-light">
                <div className="w-8 h-8 rounded-full bg-gray-100 animate-pulse" />
                <div className="w-16 h-4 bg-gray-100 rounded animate-pulse hidden lg:block" />
              </div>
            ) : user ? (
              <div className="relative ml-2 pl-3 border-l border-border-light" ref={dropdownRef}>
                <button
                  onClick={() => setIsProfileOpen(!isProfileOpen)}
                  className="flex items-center gap-2.5 p-1.5 rounded-lg hover:bg-gray-100 transition focus:outline-none"
                  aria-expanded={isProfileOpen}
                >
                  <div className="w-8 h-8 rounded-full bg-primary/10 text-primary font-bold text-sm flex items-center justify-center border border-primary/20 shadow-sm">
                    {user.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
                  </div>
                  <div className="text-left hidden lg:block">
                    <p className="text-sm font-semibold text-text-primary leading-tight max-w-[120px] truncate">
                      {user.full_name}
                    </p>
                    <p className="text-[10px] text-text-muted leading-tight capitalize">
                      {user.role === 'admin' ? 'Administrator' : 'User'}
                    </p>
                  </div>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      user.role === 'admin'
                        ? 'bg-primary/10 text-primary border border-primary/20'
                        : 'bg-gray-100 text-text-secondary border border-border-light'
                    }`}
                  >
                    {user.role === 'admin' ? 'Admin' : 'User'}
                  </span>
                  <span className="material-symbols-outlined text-text-muted text-lg transition-transform duration-200" style={{ transform: isProfileOpen ? 'rotate(180deg)' : 'none' }}>
                    expand_more
                  </span>
                </button>

                {/* Dropdown Menu */}
                {isProfileOpen && (
                  <div className="absolute right-0 mt-2 w-56 bg-bg-card rounded-xl border border-border-light shadow-card-hover py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                    <div className="px-4 py-3 border-b border-border-light">
                      <p className="text-xs font-semibold text-text-primary truncate">{user.full_name}</p>
                      <p className="text-[11px] text-text-muted truncate">{user.email}</p>
                      <div className="mt-2 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        <span className="text-[10px] font-medium text-emerald-700 capitalize">
                          {user.role === 'admin' ? 'Administrator Access' : 'Verified User'}
                        </span>
                      </div>
                    </div>

                    <div className="py-1">
                      <Link
                        href="/profile"
                        onClick={() => setIsProfileOpen(false)}
                        className="flex items-center gap-2.5 px-4 py-2 text-xs font-medium text-text-primary hover:bg-gray-50 hover:text-primary transition"
                      >
                        <span className="material-symbols-outlined text-base text-text-secondary">account_circle</span>
                        <span>Profile</span>
                      </Link>

                      <Link
                        href="/settings"
                        onClick={() => setIsProfileOpen(false)}
                        className="flex items-center gap-2.5 px-4 py-2 text-xs font-medium text-text-primary hover:bg-gray-50 hover:text-primary transition"
                      >
                        <span className="material-symbols-outlined text-base text-text-secondary">settings</span>
                        <span>Account Settings</span>
                      </Link>

                      {user.role === 'admin' && (
                        <Link
                          href="/admin"
                          onClick={() => setIsProfileOpen(false)}
                          className="flex items-center gap-2.5 px-4 py-2 text-xs font-medium text-primary hover:bg-primary/5 transition"
                        >
                          <span className="material-symbols-outlined text-base text-primary">admin_panel_settings</span>
                          <span>Admin Console</span>
                        </Link>
                      )}
                    </div>

                    <div className="pt-1 border-t border-border-light">
                      <button
                        onClick={() => {
                          setIsProfileOpen(false);
                          logout();
                        }}
                        className="w-full flex items-center gap-2.5 px-4 py-2 text-xs font-medium text-danger hover:bg-red-50 transition"
                      >
                        <span className="material-symbols-outlined text-base text-danger">logout</span>
                        <span>Sign Out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 ml-2 pl-3 border-l border-border-light">
                <Link
                  href="/login"
                  className="px-3 py-1.5 text-xs font-semibold text-text-secondary hover:text-text-primary hover:bg-gray-100 rounded-lg transition"
                >
                  Log In
                </Link>
                <Link
                  href="/signup"
                  className="px-3.5 py-1.5 text-xs font-semibold text-white bg-primary hover:bg-primary-dark rounded-lg shadow-sm shadow-primary/20 transition flex items-center gap-1.5"
                >
                  <span className="material-symbols-outlined text-sm">person_add</span>
                  <span>Sign Up</span>
                </Link>
              </div>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6">
          {children}
        </main>

        {/* Footer */}
        <footer className="px-6 py-3 border-t border-border-light text-center">
          <p className="text-xs text-text-muted">Instant Prediction · Production Risk Analytics · B.Tech Capstone Project</p>
        </footer>
      </div>
    </div>
  );
}
