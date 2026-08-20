'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Search, BarChart2, FileText, Info, Shield } from 'lucide-react';
import clsx from 'clsx';

const NAV_ITEMS = [
  { href: '/',            label: 'Dashboard',             icon: LayoutDashboard },
  { href: '/predict',     label: 'Transaction Prediction', icon: Search         },
  { href: '/analysis',   label: 'Dataset Analysis',       icon: FileText       },
  { href: '/performance', label: 'Model Performance',      icon: BarChart2      },
  { href: '/about',       label: 'About',                  icon: Info           },
];

export default function Navbar() {
  const path = usePathname();

  return (
    <aside className="fixed top-0 left-0 h-full w-64 bg-gradient-to-b from-slate-900 to-slate-800
                      border-r border-border flex flex-col z-50">
      {/* Logo */}
      <div className="px-6 py-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary/20 border border-primary/40 rounded-xl
                          flex items-center justify-center">
            <Shield className="w-5 h-5 text-primary" />
          </div>
          <div>
            <p className="font-bold text-slate-100 leading-tight">UPI Fraud</p>
            <p className="text-[10px] text-muted leading-tight">ML Prototype</p>
          </div>
        </div>
        <p className="text-[10px] text-muted mt-3 leading-relaxed">
          Not connected to NPCI / UPI network
        </p>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx('nav-link', { active: path === href })}
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span>{label}</span>
          </Link>
        ))}
      </nav>

      {/* Footer tag */}
      <div className="px-6 py-4 border-t border-border">
        <p className="text-[10px] text-muted leading-relaxed text-center">
          Instant prediction · Public dataset<br />
          B.Tech Capstone Project
        </p>
      </div>
    </aside>
  );
}
