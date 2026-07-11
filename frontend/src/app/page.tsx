'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import CodexaLogo from '@/components/CodexaLogo';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Landing() {
  const router = useRouter();

  // Pre-warm the Render backend as soon as the user visits the landing page.
  // This starts the cold-boot process early so it completes before they log in.
  useEffect(() => {
    fetch(`${API_URL}/health`, { method: 'GET', keepalive: true }).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-white dark:bg-black text-black dark:text-white p-4">
      <div className="max-w-md w-full text-center space-y-6 flex flex-col items-center">
        <CodexaLogo size="xl" className="animate-pulse" />
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          Codexa
        </h1>
        <p className="text-lg text-gray-600 dark:text-gray-400">
          Understand your Python codebase. Ask questions, get answers.
        </p>
        <div className="w-full max-w-xs pt-2">
          <button
            onClick={() => router.push('/sign-in')}
            className="w-full bg-black dark:bg-white text-white dark:text-black font-semibold py-3 px-6 rounded-xl hover:bg-gray-800 dark:hover:bg-gray-200 hover:shadow-lg hover:shadow-indigo-500/10 transition-all duration-200 border border-transparent dark:border-white cursor-pointer"
          >
            Get Started
          </button>
        </div>
      </div>
    </div>
  );
}
