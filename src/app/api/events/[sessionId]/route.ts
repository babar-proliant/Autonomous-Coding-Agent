import { proxyStreamToBackend } from '@/lib/apiProxy';
import { NextRequest } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  return proxyStreamToBackend(`/api/events/${sessionId}`);
}
