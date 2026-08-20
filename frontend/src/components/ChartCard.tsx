import type { ReactNode } from 'react';

interface ChartCardProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export default function ChartCard({ title, children, className = '' }: ChartCardProps) {
  return (
    <div className={`chart-card animate-slide-up ${className}`}>
      <p className="section-title">{title}</p>
      {children}
    </div>
  );
}
