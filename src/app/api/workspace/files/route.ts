import { NextRequest, NextResponse } from 'next/server';

const BACKEND_PORT = '8000';

// Increase route timeout for large file listings
export const maxDuration = 60; // 60 seconds max

// Get list of files in workspace - respects backend when working
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const sessionId = searchParams.get('session_id');

  if (!sessionId) {
    return NextResponse.json({ files: [], sessionId: null });
  }

  // First check if backend is alive
  try {
    const healthController = new AbortController();
    const healthTimeoutId = setTimeout(() => healthController.abort(), 3000);
    
    const healthResponse = await fetch(`http://localhost:${BACKEND_PORT}/api/health`, {
      signal: healthController.signal,
    });
    clearTimeout(healthTimeoutId);
    
    if (!healthResponse.ok) {
      return NextResponse.json({ files: [], sessionId, error: 'Backend unhealthy' });
    }
  } catch {
    return NextResponse.json({ files: [], sessionId, error: 'Backend offline' });
  }

  // Backend is alive - fetch files with longer timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 seconds

  try {
    const backendUrl = `http://localhost:${BACKEND_PORT}/api/workspace/${sessionId}`;
    
    const response = await fetch(backendUrl, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      return NextResponse.json({ files: [], sessionId, error: 'Session not found' });
    }

    const data = await response.json();
    
    // Flatten file list from backend response
    const fileList: string[] = [];
    
    if (data.files && Array.isArray(data.files)) {
      for (const item of data.files) {
        if (item.is_file) {
          fileList.push(item.path);
        } else if (item.is_dir) {
          // Fetch subdirectories (non-recursive for speed)
          const subFiles = await fetchDirectoryFiles(sessionId, item.path);
          fileList.push(...subFiles);
        }
      }
    }

    return NextResponse.json({ 
      files: fileList, 
      sessionId,
      projectPath: data.project_path || data.path
    });

  } catch (fetchError) {
    clearTimeout(timeoutId);
    
    if (fetchError instanceof Error && fetchError.name === 'AbortError') {
      return NextResponse.json({ files: [], sessionId, error: 'Request timed out - backend may be processing' });
    }
    
    console.error('Error fetching from backend:', fetchError);
    return NextResponse.json({ files: [], sessionId, error: 'Backend unavailable' });
  }
}

// Fetch files from a single directory
async function fetchDirectoryFiles(sessionId: string, dirPath: string): Promise<string[]> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 seconds per directory

  try {
    const url = `http://localhost:${BACKEND_PORT}/api/workspace/${sessionId}?path=${encodeURIComponent(dirPath)}`;
    const response = await fetch(url, { 
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    });
    clearTimeout(timeoutId);
    
    if (!response.ok) return [];
    
    const data = await response.json();
    const files: string[] = [];
    
    if (data.files && Array.isArray(data.files)) {
      for (const item of data.files) {
        if (item.is_file) {
          files.push(item.path);
        }
        // Skip deeper subdirectories to keep response fast
      }
    }
    
    return files;
  } catch {
    clearTimeout(timeoutId);
    return [];
  }
}
