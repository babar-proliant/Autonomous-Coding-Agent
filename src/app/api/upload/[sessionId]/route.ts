import { proxyMultipartToBackend } from '@/lib/apiProxy';
import { NextRequest } from 'next/server';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  const formData = await request.formData();
  return proxyMultipartToBackend(`/api/upload/${sessionId}`, formData);
}
