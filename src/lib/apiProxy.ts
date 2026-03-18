/**
 * API Proxy utility for forwarding requests to the Python backend.
 * The Python backend runs on port 8000, accessible via XTransformPort query param.
 */

const BACKEND_PORT = '8000';

interface ProxyOptions {
  method?: 'GET' | 'POST' | 'DELETE' | 'PUT';
  body?: unknown;
  headers?: Record<string, string>;
}

/**
 * Forward an API request to the Python backend.
 */
export async function proxyToBackend(
  path: string,
  options: ProxyOptions = {}
): Promise<Response> {
  const { method = 'GET', body, headers = {} } = options;

  // Build URL with XTransformPort for gateway routing
  const baseUrl = process.env.NODE_ENV === 'development' 
    ? `http://localhost:${BACKEND_PORT}${path}`
    : `${path}?XTransformPort=${BACKEND_PORT}`;

  const fetchOptions: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
	signal: AbortSignal.timeout(path.includes('/status') ? 3600000 : 3600000),
  };

  if (body && method !== 'GET') {
    fetchOptions.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(baseUrl, fetchOptions);
    
    // Check if response is OK before trying to parse JSON
    if (!response.ok) {
      let errorMessage = 'Request failed';
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.error || errorMessage;
      } catch {
        // Response wasn't JSON, use status text
        errorMessage = response.statusText || `HTTP ${response.status}`;
      }
      return Response.json(
        { error: errorMessage, status: response.status },
        { status: response.status }
      );
    }
    
    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch (error) {
    console.error(`Proxy error for ${path}:`, error);
    return Response.json(
      { error: 'Failed to connect to backend', details: String(error) },
      { status: 503 }
    );
  }
}

/**
 * Forward a streaming request (SSE) to the Python backend.
 */
export async function proxyStreamToBackend(path: string): Promise<Response> {
  const baseUrl = `http://localhost:${BACKEND_PORT}${path}`;

  try {
    const response = await fetch(baseUrl, {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });

    if (!response.ok) {
      return Response.json(
        { error: 'Failed to connect to backend' },
        { status: response.status }
      );
    }

    // Return the stream directly without buffering
    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body?.getReader();
        if (!reader) {
          controller.close();
          return;
        }

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              controller.close();
              break;
            }
            controller.enqueue(value);
          }
        } catch (error) {
          controller.error(error);
        }
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    });
  } catch (error) {
    console.error(`Stream proxy error for ${path}:`, error);
    return Response.json(
      { error: 'Failed to connect to backend', details: String(error) },
      { status: 503 }
    );
  }
}

/**
 * Forward a multipart form request to the Python backend.
 */
export async function proxyMultipartToBackend(
  path: string,
  formData: FormData
): Promise<Response> {
  const baseUrl = process.env.NODE_ENV === 'development'
    ? `http://localhost:${BACKEND_PORT}${path}`
    : `${path}?XTransformPort=${BACKEND_PORT}`;

  try {
    const response = await fetch(baseUrl, {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch (error) {
    console.error(`Multipart proxy error for ${path}:`, error);
    return Response.json(
      { error: 'Failed to connect to backend', details: String(error) },
      { status: 503 }
    );
  }
}
