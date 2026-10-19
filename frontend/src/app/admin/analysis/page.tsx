'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminAnalysisRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/analysis');
  }, [router]);
  return null;
}
