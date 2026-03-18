import { NextRequest, NextResponse } from 'next/server';

const BACKEND_PORT = '8000';

// Get file content from backend
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const filePath = searchParams.get('path');
    const sessionId = searchParams.get('session_id');

    if (!filePath) {
      return NextResponse.json({ error: 'path is required' }, { status: 400 });
    }

    if (!sessionId) {
      return NextResponse.json({ error: 'session_id is required' }, { status: 400 });
    }

    // Fetch from backend
    const backendUrl = `http://localhost:${BACKEND_PORT}/api/file/${sessionId}?path=${encodeURIComponent(filePath)}`;
    
    try {
      const response = await fetch(backendUrl);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        return NextResponse.json(
          { error: errorData.detail || errorData.error || 'Failed to read file' },
          { status: response.status }
        );
      }

      const data = await response.json();
      
      return NextResponse.json({
        path: filePath,
        content: data.content,
        size: data.size || data.content?.length || 0,
      });

    } catch (fetchError) {
      console.error('Error fetching from backend:', fetchError);
      return NextResponse.json({ error: 'Backend unavailable' }, { status: 503 });
    }
  } catch (error) {
    console.error('Error reading file:', error);
    return NextResponse.json(
      { error: 'Failed to read file' },
      { status: 500 }
    );
  }
}
