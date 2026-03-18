import { NextResponse } from 'next/server';

const BACKEND_PORT = '8000';

// Proxy to backend status - respects when backend is working
export async function GET() {
  try {
    // First do a quick health check
    const healthController = new AbortController();
    const healthTimeoutId = setTimeout(() => healthController.abort(), 3000);

    try {
      const healthResponse = await fetch(`http://localhost:${BACKEND_PORT}/api/health`, {
        signal: healthController.signal,
      });
      clearTimeout(healthTimeoutId);

      if (!healthResponse.ok) {
        return NextResponse.json({
          status: 'degraded',
          system: { cpu_percent: 0, memory_percent: 0, disk_percent: 0 },
          models: { loaded: [] },
          active_sessions: 0,
        });
      }
    } catch {
      clearTimeout(healthTimeoutId);
      // Backend is not responding
      return NextResponse.json({
        status: 'offline',
        system: { cpu_percent: 0, memory_percent: 0, disk_percent: 0 },
        models: { loaded: [] },
        active_sessions: 0,
      });
    }

    // Backend is alive - get full status with longer timeout
    // This allows the backend to complete its work
    const statusController = new AbortController();
    const statusTimeoutId = setTimeout(() => statusController.abort(), 30000); // 30 seconds

    try {
      const response = await fetch(`http://localhost:${BACKEND_PORT}/api/status`, {
        signal: statusController.signal,
        headers: { 'Accept': 'application/json' },
      });
      
      clearTimeout(statusTimeoutId);
      
      if (!response.ok) {
        return NextResponse.json({
          status: 'degraded',
          system: { cpu_percent: 0, memory_percent: 0, disk_percent: 0 },
          models: { loaded: [] },
          active_sessions: 0,
        });
      }
      
      const data = await response.json();
      return NextResponse.json(data);
    } catch {
      clearTimeout(statusTimeoutId);
      // Health check passed but status failed - backend is busy
      return NextResponse.json({
        status: 'busy',
        system: { cpu_percent: 0, memory_percent: 0, disk_percent: 0 },
        models: { loaded: [] },
        active_sessions: 0,
      });
    }
  } catch {
    return NextResponse.json({
      status: 'error',
      system: { cpu_percent: 0, memory_percent: 0, disk_percent: 0 },
      models: { loaded: [] },
      active_sessions: 0,
    });
  }
}
