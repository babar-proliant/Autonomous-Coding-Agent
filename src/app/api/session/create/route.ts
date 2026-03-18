import { proxyToBackend } from '@/lib/apiProxy';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToBackend('/api/session/create', { method: 'POST', body });
}
