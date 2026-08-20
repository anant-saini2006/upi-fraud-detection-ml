import clsx from 'clsx';

type RiskLevel = 'HIGH' | 'MEDIUM' | 'LOW';

const MAP: Record<RiskLevel, { cls: string; dot: string; label: string }> = {
  HIGH:   { cls: 'badge-high',   dot: 'bg-red-400',   label: '🔴 HIGH'   },
  MEDIUM: { cls: 'badge-medium', dot: 'bg-amber-400', label: '🟡 MEDIUM' },
  LOW:    { cls: 'badge-low',    dot: 'bg-green-400', label: '🟢 LOW'    },
};

export default function RiskBadge({ level }: { level: RiskLevel }) {
  const { cls, label } = MAP[level] ?? MAP.LOW;
  return <span className={cls}>{label}</span>;
}
