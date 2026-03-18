import { proxyToBackend } from '@/lib/apiProxy';
import { NextRequest } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  return proxyToBackend(`/api/session/${sessionId}`, { method: 'GET' });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  return proxyToBackend(`/api/session/${sessionId}`, { method: 'DELETE' });
}
