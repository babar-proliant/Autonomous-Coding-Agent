import { NextRequest, NextResponse } from 'next/server';
import archiver from 'archiver';

const BACKEND_PORT = '8000';

// Download project as zip
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const sessionId = searchParams.get('session_id');

    if (!sessionId) {
      return NextResponse.json({ error: 'session_id is required' }, { status: 400 });
    }

    // Get session info from backend
    const sessionUrl = `http://localhost:${BACKEND_PORT}/api/workspace/${sessionId}`;
    const sessionResponse = await fetch(sessionUrl);
    
    if (!sessionResponse.ok) {
      return NextResponse.json({ error: 'Session not found' }, { status: 404 });
    }

    // Get all files
    const filesUrl = `http://localhost:${BACKEND_PORT}/api/workspace/${sessionId}`;
    const filesResponse = await fetch(filesUrl);
    const filesData = await filesResponse.json();
    
    // Recursively get all file paths
    const filePaths: string[] = [];
    await getAllFilePaths(sessionId, '', filePaths);

    // Create a zip archive in memory
    const archive = archiver('zip');
    const chunks: Buffer[] = [];

    archive.on('data', (chunk) => {
      chunks.push(chunk);
    });

    // Fetch and add each file to the archive
    for (const filePath of filePaths) {
      try {
        const fileUrl = `http://localhost:${BACKEND_PORT}/api/file/${sessionId}?path=${encodeURIComponent(filePath)}`;
        const fileResponse = await fetch(fileUrl);
        
        if (fileResponse.ok) {
          const fileData = await fileResponse.json();
          if (fileData.content) {
            archive.append(fileData.content, { name: filePath });
          }
        }
      } catch (error) {
        console.error(`Error fetching file ${filePath}:`, error);
      }
    }

    // Finalize the archive
    await archive.finalize();

    // Return zip file
    const zipBuffer = Buffer.concat(chunks);

    return new NextResponse(zipBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': `attachment; filename="project-${sessionId.slice(0, 8)}.zip"`,
      },
    });
  } catch (error) {
    console.error('Error creating zip:', error);
    return NextResponse.json(
      { error: 'Failed to create download' },
      { status: 500 }
    );
  }
}

// Recursively get all file paths from backend
async function getAllFilePaths(sessionId: string, dirPath: string, filePaths: string[]): Promise<void> {
  const url = `http://localhost:${BACKEND_PORT}/api/workspace/${sessionId}${dirPath ? `?path=${encodeURIComponent(dirPath)}` : ''}`;
  
  try {
    const response = await fetch(url);
    if (!response.ok) return;
    
    const data = await response.json();
    const files = data.files || [];
    
    for (const item of files) {
      if (item.is_file) {
        filePaths.push(item.path);
      } else if (item.is_dir) {
        await getAllFilePaths(sessionId, item.path, filePaths);
      }
    }
  } catch (error) {
    console.error(`Error fetching directory ${dirPath}:`, error);
  }
}
