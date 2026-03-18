import { proxyToBackend } from '@/lib/apiProxy';

export async function GET() {
  return proxyToBackend('/api/tools', { method: 'GET' });
}
