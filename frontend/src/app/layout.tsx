import type { Metadata } from 'next';
import { type ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'UPI Fraud Detection — ML Prototype',
  description:
    'A machine-learning prototype for UPI-style digital payment fraud detection. ' +
    'Trained on a digital-payments dataset. Not connected to the real UPI network.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bg-main min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
