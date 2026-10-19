'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminPredictRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/predict');
  }, [router]);
  return null;
}
