'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';

const navItems = [
  { href: '/', icon: 'dashboard', label: 'Dashboard' },
  { href: '/predict', icon: 'shield', label: 'Transaction Prediction' },
  { href: '/analysis', icon: 'bar_chart', label: 'Dataset Analysis' },
  { href: '/performance', icon: 'speed', label: 'Model Performance' },
  { href: '/about', icon: 'info', label: 'About' },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen flex bg-bg-main">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-64 bg-bg-card border-r border-border-light shadow-sidebar fixed top-0 left-0 h-full z-40">
        {/* Logo */}
        <div className="p-5 border-b border-border-light">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-white text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>shield</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary leading-tight">UPI Fraud</h1>
              <p className="text-xs text-text-muted leading-tight">Detection</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
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
        </nav>

        {/* Footer badge */}
        <div className="p-4 border-t border-border-light">
          <div className="flex items-center gap-2 px-3 py-2 bg-orange-50 border border-orange-200 rounded-lg">
            <span className="material-symbols-outlined text-accent text-lg">science</span>
            <div>
              <p className="text-xs font-semibold text-accent">Prototype</p>
              <p className="text-[10px] text-orange-600/80 leading-tight">Not connected to<br/>NPCI / UPI</p>
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
              {navItems.find(n => n.href === pathname)?.label || 'Dashboard'}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 bg-orange-50 border border-orange-200 rounded-full text-xs font-medium text-orange-700">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse"></span>
              Prototype — not connected to NPCI / UPI
            </span>
            <button className="p-2 text-text-secondary hover:text-text-primary hover:bg-gray-100 rounded-lg transition-colors">
              <span className="material-symbols-outlined text-xl">call</span>
            </button>
            <button className="p-2 text-text-secondary hover:text-text-primary hover:bg-gray-100 rounded-lg transition-colors relative">
              <span className="material-symbols-outlined text-xl">notifications</span>
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-danger rounded-full"></span>
            </button>
            <div className="flex items-center gap-2 ml-2 pl-3 border-l border-border-light">
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="material-symbols-outlined text-primary text-lg">person</span>
              </div>
              <span className="text-sm font-medium text-text-primary hidden lg:inline">Admin</span>
              <span className="material-symbols-outlined text-text-muted text-lg">expand_more</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6">
          {children}
        </main>

        {/* Footer */}
        <footer className="px-6 py-3 border-t border-border-light text-center">
          <p className="text-xs text-text-muted">Instant prediction · Dataset-backed prototype · B.Tech Capstone Project</p>
        </footer>
      </div>
    </div>
  );
}
