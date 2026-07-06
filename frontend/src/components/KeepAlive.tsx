'use client';

import { useEffect } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const PING_INTERVAL_MS = 10 * 60 * 1000; // Every 10 minutes

/**
 * KeepAlive component - silently pings the Render backend every 10 minutes
 * to prevent Render's free-tier container from sleeping (which causes 1-2 min
 * cold start delays for users trying to log in after a period of inactivity).
 */
export default function KeepAlive() {
  useEffect(() => {
    const ping = () => {
      fetch(`${API_URL}/health`, { method: 'GET' }).catch(() => {
        // Silently ignore errors - this is best-effort
      });
    };

    // Ping immediately on page load, then every 10 minutes
    ping();
    const interval = setInterval(ping, PING_INTERVAL_MS);

    return () => clearInterval(interval);
  }, []);

  return null; // Renders nothing visible
}
