/**
 * TypeScript types for the Autonomous Coding Agent frontend.
 */

// ============================================
// Session Types
// ============================================

export interface Session {
  id: string;
  project_name: string;
  project_path: string;
  status: 'active' | 'ended' | 'error';
  created_at?: string;
  updated_at?: string;
}

// ============================================
// Message Types
// ============================================

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'agent' | 'tool' | 'system';
  content: string;
  importance_score?: number;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

// ============================================
// Task Types
// ============================================

export interface Task {
  id: string;
  session_id: string;
  parent_task_id?: string;
  agent_name: string;
  description: string;
  task_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  priority: number;
  dependencies: string[];
  result?: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
}

// ============================================
// Event Types
// ============================================

export type EventType =
  // Session events
  | 'session_start'
  | 'session_end'
  // Thinking events (streaming)
  | 'thinking_start'
  | 'thinking_stream'
  | 'thinking_end'
  // Tool events
  | 'tool_start'
  | 'tool_output'
  | 'tool_result'
  | 'tool_error'
  // Task events
  | 'task_created'
  | 'task_started'
  | 'task_progress'
  | 'task_completed'
  | 'task_failed'
  // Agent events
  | 'agent_switch'
  | 'agent_activity'
  // Model events
  | 'model_load'
  | 'model_unload'
  // File events
  | 'file_created'
  | 'file_modified'
  | 'file_deleted'
  // Checkpoint events
  | 'checkpoint_created'
  | 'rollback_complete'
  // Error events
  | 'error'
  | 'warning'
  // Control events
  | 'user_input_required'
  | 'user_approval_required'
  | 'done';

export interface AgentEvent {
  event_type: EventType;
  session_id: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// ============================================
// Tool Types
// ============================================

export interface ToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
  choices?: unknown[];
}

export interface ToolSchema {
  name: string;
  description: string;
  category: string;
  risk: 'low' | 'medium' | 'high';
  requires_confirmation: boolean;
  timeout_seconds: number;
  parameters: ToolParameter[];
}

export interface ToolResult {
  tool_name: string;
  status: 'success' | 'failed' | 'blocked' | 'timeout' | 'pending' | 'running';
  result?: unknown;
  error?: string;
  execution_time_ms: number;
  metadata?: Record<string, unknown>;
}

// ============================================
// File System Types
// ============================================

export interface FileEntry {
  name: string;
  path: string;
  is_file: boolean;
  is_dir: boolean;
  size: number;
  modified?: number;
}

export interface WorkspaceState {
  path: string;
  files: FileEntry[];
}

// ============================================
// Model Types
// ============================================

export interface ModelState {
  name: string;
  state: 'unloaded' | 'loading' | 'loaded' | 'error' | 'unloading';
  vram_usage_gb?: number;
}

export interface ModelsStatus {
  loaded_models: string[];
  model_states: Record<string, string>;
  vram_usage: Record<string, number>;
  loaded: string[];
}

// ============================================
// System Status Types
// ============================================

export interface SystemStatus {
  status: 'operational' | 'degraded' | 'error';
  active_sessions: number;
  system: {
    cpu_percent: number;
    memory_percent: number;
    disk_percent: number;
  };
  models: {
    loaded: string[];
    loaded_models?: string[];
  };
}

// ============================================
// Chat Types
// ============================================

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  session_id: string;
  status: 'processing' | 'error';
}

// ============================================
// API Response Types
// ============================================

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}

// ============================================
// UI State Types
// ============================================

export interface AgentActivity {
  id: string;
  type: EventType;
  agent?: string;
  content: string;
  timestamp: Date;
  expanded?: boolean;
  metadata?: Record<string, unknown>;
}

export interface Tab {
  id: string;
  name: string;
  type: 'file' | 'tool' | 'graph';
  path?: string;
  content?: string;
  isActive: boolean;
}

// ============================================
// Store Types (for exports)
// ============================================

export interface ChatState {
  session: Session | null;
  setSession: (session: Session | null) => void;
  messages: Message[];
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  activities: AgentActivity[];
  addActivity: (activity: Omit<AgentActivity, 'id'> & { id?: string }) => void;
  updateActivity: (id: string, updates: Partial<AgentActivity>) => void;
  clearActivities: () => void;
  isStreaming: boolean;
  setIsStreaming: (streaming: boolean) => void;
  currentStreamingContent: string;
  appendStreamingContent: (content: string) => void;
  clearStreamingContent: () => void;
  currentAgent: string;
  setCurrentAgent: (agent: string) => void;
  inputValue: string;
  setInputValue: (value: string) => void;
}
