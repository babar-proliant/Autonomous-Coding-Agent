'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable';
import {
  ChevronRight,
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  Download,
  Eye,
  Code,
  RefreshCw,
  AlertCircle,
  Plus,
  Settings,
  Upload,
  Loader2,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// Dynamically import Monaco Editor (no SSR)
const MonacoEditor = dynamic(
  () => import('@monaco-editor/react').then((mod) => mod.default),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    ),
  }
);

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: FileNode[];
}

interface WorkspacePanelProps {
  sessionId: string | null;
  onRefresh?: () => void;
  onNewSession?: () => void;
  onOpenSettings?: () => void;
}

// Get language from file extension for Monaco
function getLanguageFromPath(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() || '';
  const languageMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    json: 'json',
    html: 'html',
    htm: 'html',
    css: 'css',
    scss: 'scss',
    sass: 'scss',
    less: 'less',
    md: 'markdown',
    mdx: 'markdown',
    py: 'python',
    rb: 'ruby',
    java: 'java',
    go: 'go',
    rs: 'rust',
    cpp: 'cpp',
    c: 'c',
    h: 'c',
    hpp: 'cpp',
    cs: 'csharp',
    php: 'php',
    swift: 'swift',
    kt: 'kotlin',
    scala: 'scala',
    sql: 'sql',
    yaml: 'yaml',
    yml: 'yaml',
    xml: 'xml',
    sh: 'shell',
    bash: 'shell',
    zsh: 'shell',
    dockerfile: 'dockerfile',
    vue: 'vue',
    svelte: 'svelte',
  };
  return languageMap[ext] || 'plaintext';
}

// File icon based on extension
function getFileIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase();
  const codeExtensions = ['ts', 'tsx', 'js', 'jsx', 'py', 'json', 'html', 'css', 'scss', 'md', 'yaml', 'yml', 'go', 'rs', 'java', 'cpp', 'c'];

  if (codeExtensions.includes(ext || '')) {
    return <FileCode className="h-4 w-4 text-blue-500" />;
  }
  return <FileText className="h-4 w-4 text-muted-foreground" />;
}

// Build file tree from flat list
function buildFileTree(files: string[]): FileNode[] {
  const root: FileNode[] = [];
  const nodeMap = new Map<string, FileNode>();

  const sortedFiles = [...files].sort();

  for (const filePath of sortedFiles) {
    const parts = filePath.split('/').filter(Boolean);
    let currentPath = '';
    let currentLevel = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      let node = nodeMap.get(currentPath);

      if (!node) {
        node = {
          name: part,
          path: currentPath,
          type: isFile ? 'file' : 'folder',
          children: isFile ? undefined : [],
        };
        nodeMap.set(currentPath, node);
        currentLevel.push(node);
      }

      if (!isFile && node.children) {
        currentLevel = node.children;
      }
    }
  }

  return root;
}

// File tree item component
function FileTreeItem({
  node,
  level,
  selectedFile,
  onSelectFile,
  expandedFolders,
  onToggleFolder,
}: {
  node: FileNode;
  level: number;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
}) {
  const isExpanded = expandedFolders.has(node.path);
  const isSelected = selectedFile === node.path;

  if (node.type === 'folder') {
    return (
      <div>
        <button
          className={cn(
            'flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-accent',
            isSelected && 'bg-accent'
          )}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
          onClick={() => onToggleFolder(node.path)}
        >
          <ChevronRight
            className={cn(
              'h-3 w-3 shrink-0 text-muted-foreground transition-transform',
              isExpanded && 'rotate-90'
            )}
          />
          {isExpanded ? (
            <FolderOpen className="h-4 w-4 text-amber-500" />
          ) : (
            <Folder className="h-4 w-4 text-amber-500" />
          )}
          <span className="truncate">{node.name}</span>
        </button>
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeItem
                key={child.path}
                node={child}
                level={level + 1}
                selectedFile={selectedFile}
                onSelectFile={onSelectFile}
                expandedFolders={expandedFolders}
                onToggleFolder={onToggleFolder}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      className={cn(
        'flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-accent',
        isSelected && 'bg-accent font-medium'
      )}
      style={{ paddingLeft: `${level * 12 + 20}px` }}
      onClick={() => onSelectFile(node.path)}
    >
      {getFileIcon(node.name)}
      <span className="truncate">{node.name}</span>
    </button>
  );
}

// Monaco Editor wrapper
function CodeEditor({
  content,
  language,
  theme,
}: {
  content: string;
  language: string;
  theme: 'light' | 'dark';
}) {
  return (
    <MonacoEditor
      height="100%"
      language={language}
      value={content}
      theme={theme === 'dark' ? 'vs-dark' : 'light'}
      options={{
        readOnly: true,
        minimap: { enabled: true },
        fontSize: 13,
        lineNumbers: 'on',
        wordWrap: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        folding: true,
        foldingHighlight: true,
        showFoldingControls: 'mouseover',
        bracketPairColorization: { enabled: true },
        renderLineHighlight: 'all',
        cursorBlinking: 'smooth',
        smoothScrolling: true,
        padding: { top: 10 },
      }}
    />
  );
}

// Preview viewer for HTML files - uses iframe with src for proper relative path resolution
function PreviewViewer({ 
  content, 
  sessionId, 
  filePath 
}: { 
  content: string; 
  sessionId: string | null;
  filePath: string;
}) {
  // Use path-based raw file API for proper relative path resolution
  // URL format: /api/workspace/raw/{sessionId}/{filePath}
  const rawFileUrl = sessionId 
    ? `/api/workspace/raw/${sessionId}/${filePath}`
    : null;
  
  if (rawFileUrl) {
    return (
      <div className="h-full bg-white">
        <iframe
          src={rawFileUrl}
          className="h-full w-full border-0"
          title="Preview"
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        />
      </div>
    );
  }
  
  // Fallback to srcDoc for non-session context
  return (
    <div className="h-full bg-white">
      <iframe
        srcDoc={content}
        className="h-full w-full border-0"
        title="Preview"
        sandbox="allow-scripts allow-same-origin"
      />
    </div>
  );
}

export function WorkspacePanel({ sessionId, onRefresh, onNewSession, onOpenSettings }: WorkspacePanelProps) {
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['src']));
  const [viewMode, setViewMode] = useState<'code' | 'preview'>('code');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');
  
  // Upload state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ total: number; uploaded: number } | null>(null);
  const [uploadResult, setUploadResult] = useState<{ success: number; errors: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const fileTree = buildFileTree(files);

  // Detect theme
  useEffect(() => {
    const isDark = document.documentElement.classList.contains('dark');
    setTheme(isDark ? 'dark' : 'light');

    // Watch for theme changes
    const observer = new MutationObserver(() => {
      const isDark = document.documentElement.classList.contains('dark');
      setTheme(isDark ? 'dark' : 'light');
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => observer.disconnect();
  }, []);

  // Fetch file list
  const fetchFiles = useCallback(async () => {
    try {
      const url = sessionId
        ? `/api/workspace/files?session_id=${sessionId}`
        : `/api/workspace/files`;

      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setFiles(data.files || []);
      }
    } catch (error) {
      console.error('Error fetching files:', error);
    }
  }, [sessionId]);

  // Fetch file content
  const fetchFileContent = useCallback(async (filePath: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const url = sessionId
        ? `/api/workspace/file?session_id=${sessionId}&path=${encodeURIComponent(filePath)}`
        : `/api/workspace/file?path=${encodeURIComponent(filePath)}`;

      const response = await fetch(url);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to load file');
      }

      const data = await response.json();
      setFileContent(data.content || '');
    } catch (error) {
      console.error('Error fetching file content:', error);
      setError(error instanceof Error ? error.message : 'Failed to load file');
      setFileContent('');
    }
    setIsLoading(false);
  }, [sessionId]);

  // Initial fetch and polling
  useEffect(() => {
    void fetchFiles();
    const interval = setInterval(() => void fetchFiles(), 10000);
    return () => clearInterval(interval);
  }, [fetchFiles]);

  // Handle file selection
  const handleSelectFile = (path: string) => {
    setSelectedFile(path);
    fetchFileContent(path);

    // Auto-switch to preview for HTML files
    const ext = path.split('.').pop()?.toLowerCase();
    if (ext === 'html' || ext === 'htm') {
      setViewMode('preview');
    } else {
      setViewMode('code');
    }
  };

  // Handle folder toggle
  const handleToggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  // Download single file
  const handleDownloadFile = () => {
    if (!selectedFile || !fileContent) return;

    const blob = new Blob([fileContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = selectedFile.split('/').pop() || 'file';
    a.click();
    URL.revokeObjectURL(url);
  };

  // Download project as zip
  const handleDownloadProject = async () => {
    try {
      const url = sessionId
        ? `/api/workspace/download?session_id=${sessionId}`
        : `/api/workspace/download`;

      const response = await fetch(url);
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'project.zip';
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Error downloading project:', error);
    }
  };

  // Handle file/folder upload
  const handleUpload = async (fileList: FileList, isFolder: boolean = false) => {
    if (!sessionId || fileList.length === 0) return;
    
    setIsUploading(true);
    setUploadProgress({ total: fileList.length, uploaded: 0 });
    setUploadResult(null);
    
    try {
      const formData = new FormData();
      
      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        // For folder uploads, preserve the relative path
        const relativePath = isFolder && file.webkitRelativePath 
          ? file.webkitRelativePath 
          : file.name;
        
        // Create a new file with the correct path
        const newFile = new File([file], relativePath, { type: file.type });
        formData.append('files', newFile);
        setUploadProgress({ total: fileList.length, uploaded: i + 1 });
      }
      
      const response = await fetch(`/api/workspace/upload?session_id=${sessionId}`, {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Upload failed');
      }
      
      const result = await response.json();
      setUploadResult({ 
        success: result.total_uploaded || 0, 
        errors: result.total_errors || 0 
      });
      
      // Refresh file list after successful upload
      if (result.total_uploaded > 0) {
        await fetchFiles();
      }
      
      // Clear result after 3 seconds
      setTimeout(() => setUploadResult(null), 3000);
      
    } catch (error) {
      console.error('Upload error:', error);
      setUploadResult({ success: 0, errors: 1 });
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
    }
  };

  // Handle refresh
  const handleRefresh = () => {
    fetchFiles();
    onRefresh?.();
  };

  // Handle new session
  const handleNewSession = () => {
    setFiles([]);
    setSelectedFile(null);
    setFileContent('');
    onNewSession?.();
  };

  // Check if file is previewable
  const isPreviewable = selectedFile && ['html', 'htm'].includes(
    selectedFile.split('.').pop()?.toLowerCase() || ''
  );

  return (
    <div className="flex h-full flex-col border-l border-border">
      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && handleUpload(e.target.files, false)}
      />
      <input
        ref={folderInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && handleUpload(e.target.files, true)}
        // @ts-expect-error webkitdirectory is not in the types
        webkitdirectory=""
        directory=""
      />
      
      {/* Header with Action Buttons */}
      <div className="flex items-center justify-between border-b border-border bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-1">
          {/* Code/Preview Toggle */}
          <div className="flex rounded-lg border border-border p-0.5">
            <Button
              variant={viewMode === 'code' ? 'default' : 'ghost'}
              size="sm"
              className="h-7 px-2"
              onClick={() => setViewMode('code')}
            >
              <Code className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === 'preview' ? 'default' : 'ghost'}
              size="sm"
              className="h-7 px-2"
              onClick={() => setViewMode('preview')}
              disabled={!isPreviewable}
            >
              <Eye className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* Upload Status */}
          {isUploading && uploadProgress && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>{uploadProgress.uploaded}/{uploadProgress.total}</span>
            </div>
          )}
          
          {/* Upload Result */}
          {uploadResult && (
            <div className="flex items-center gap-1 text-xs">
              {uploadResult.success > 0 && (
                <span className="flex items-center gap-0.5 text-green-500">
                  <CheckCircle2 className="h-3 w-3" />
                  {uploadResult.success}
                </span>
              )}
              {uploadResult.errors > 0 && (
                <span className="flex items-center gap-0.5 text-red-500">
                  <XCircle className="h-3 w-3" />
                  {uploadResult.errors}
                </span>
              )}
            </div>
          )}
          
          {/* Upload File Button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => fileInputRef.current?.click()}
            disabled={!sessionId || isUploading}
            title="Upload Files"
          >
            <Upload className="h-4 w-4" />
          </Button>
          
          {/* Upload Folder Button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => folderInputRef.current?.click()}
            disabled={!sessionId || isUploading}
            title="Upload Folder"
          >
            <Folder className="h-4 w-4" />
          </Button>
          
          {/* New Session Button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={handleNewSession}
            title="New Session"
          >
            <Plus className="h-4 w-4" />
          </Button>
          
          {/* Refresh Button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={handleRefresh}
            title="Refresh Files"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          
          {/* Settings Button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={onOpenSettings}
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </Button>
          
          {/* Download Project Button */}
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1"
            onClick={handleDownloadProject}
            disabled={files.length === 0}
          >
            <Download className="h-4 w-4" />
            <span className="hidden sm:inline">Download</span>
          </Button>
        </div>
      </div>

      {/* Main content with resizable panels */}
      <ResizablePanelGroup direction="horizontal" className="flex-1">
        {/* File Tree Panel */}
        <ResizablePanel defaultSize={25} minSize={15} maxSize={40}>
          <ScrollArea className="h-full bg-muted/20">
            {files.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-4 text-center">
                <Folder className="h-8 w-8 text-muted-foreground/50" />
                <p className="mt-2 text-sm text-muted-foreground">No files yet</p>
                <p className="text-xs text-muted-foreground">
                  Ask the agent to create files
                </p>
              </div>
            ) : (
              <div className="py-2">
                {fileTree.map((node) => (
                  <FileTreeItem
                    key={node.path}
                    node={node}
                    level={0}
                    selectedFile={selectedFile}
                    onSelectFile={handleSelectFile}
                    expandedFolders={expandedFolders}
                    onToggleFolder={handleToggleFolder}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Code/Preview Panel */}
        <ResizablePanel defaultSize={75}>
          {selectedFile ? (
            <div className="flex h-full flex-col">
              {/* File header */}
              <div className="flex items-center justify-between border-b border-border bg-muted/10 px-3 py-1.5">
                <div className="flex items-center gap-2">
                  {getFileIcon(selectedFile)}
                  <span className="text-sm font-medium">{selectedFile}</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2"
                  onClick={handleDownloadFile}
                  disabled={!fileContent}
                >
                  <Download className="h-3 w-3" />
                </Button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-hidden">
                {isLoading ? (
                  <div className="flex h-full items-center justify-center">
                    <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : error ? (
                  <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
                    <AlertCircle className="h-8 w-8 text-destructive" />
                    <p className="text-sm text-destructive">{error}</p>
                  </div>
                ) : viewMode === 'preview' && isPreviewable ? (
                  <PreviewViewer 
                    content={fileContent} 
                    sessionId={sessionId}
                    filePath={selectedFile}
                  />
                ) : (
                  <CodeEditor
                    content={fileContent}
                    language={getLanguageFromPath(selectedFile)}
                    theme={theme}
                  />
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <FileCode className="h-12 w-12 text-muted-foreground/30" />
              <p className="mt-2 text-sm text-muted-foreground">No file selected</p>
              <p className="text-xs text-muted-foreground">
                Click a file in the tree to view it
              </p>
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
