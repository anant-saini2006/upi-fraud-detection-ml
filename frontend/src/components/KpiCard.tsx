import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';

interface KpiCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  color?: 'blue' | 'red' | 'green' | 'amber' | 'purple';
  sub?: string;
}

const COLOR_MAP = {
  blue:   { icon: 'text-blue-400',   val: 'text-blue-400',   bg: 'bg-blue-400/10'   },
  red:    { icon: 'text-red-400',    val: 'text-red-400',    bg: 'bg-red-400/10'    },
  green:  { icon: 'text-green-400',  val: 'text-green-400',  bg: 'bg-green-400/10'  },
  amber:  { icon: 'text-amber-400',  val: 'text-amber-400',  bg: 'bg-amber-400/10'  },
  purple: { icon: 'text-purple-400', val: 'text-purple-400', bg: 'bg-purple-400/10' },
};

export default function KpiCard({ label, value, icon: Icon, color = 'blue', sub }: KpiCardProps) {
  const c = COLOR_MAP[color];
  return (
    <div className="kpi-card animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <p className="kpi-label">{label}</p>
          <p className={clsx('kpi-value', c.val)}>{value}</p>
          {sub && <p className="text-xs text-muted mt-1">{sub}</p>}
        </div>
        <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center', c.bg)}>
          <Icon className={clsx('w-5 h-5', c.icon)} />
        </div>
      </div>
    </div>
  );
}
