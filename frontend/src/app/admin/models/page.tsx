'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminModelsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/performance');
  }, [router]);
  return null;
}
