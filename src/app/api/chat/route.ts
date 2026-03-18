import { proxyToBackend } from '@/lib/apiProxy';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyToBackend('/api/chat', { method: 'POST', body });
}
