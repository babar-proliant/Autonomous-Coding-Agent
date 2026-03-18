import { proxyToBackend } from '@/lib/apiProxy';
import { NextRequest } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  const searchParams = request.nextUrl.searchParams;
  const path = searchParams.get('path') || '';
  return proxyToBackend(`/api/file/${sessionId}?path=${encodeURIComponent(path)}`, { method: 'GET' });
}
