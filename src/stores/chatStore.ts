/**
 * Zustand store for chat state management.
 */

import { create } from 'zustand';
import type { Message, Session, AgentActivity, EventType } from '@/types';

interface ChatState {
  // Session
  session: Session | null;
  setSession: (session: Session | null) => void;

  // Messages
  messages: Message[];
  addMessage: (message: Omit<Message, 'id'> & { id?: string }) => void;
  clearMessages: () => void;

  // Activities (for display in activity panel)
  activities: AgentActivity[];
  addActivity: (activity: Omit<AgentActivity, 'id'> & { id?: string }) => void;
  updateActivity: (id: string, updates: Partial<AgentActivity>) => void;
  clearActivities: () => void;

  // Streaming state
  isStreaming: boolean;
  setIsStreaming: (streaming: boolean) => void;
  currentStreamingContent: string;
  appendStreamingContent: (content: string) => void;
  clearStreamingContent: () => void;

  // Current agent
  currentAgent: string;
  setCurrentAgent: (agent: string) => void;

  // Input
  inputValue: string;
  setInputValue: (value: string) => void;
}

export const useChatStore = create<ChatState>()((set) => ({
  // Session
  session: null,
  setSession: (session) => set({ session }),

  // Messages
  messages: [],
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, { 
        ...message, 
        id: message.id || `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}` 
      } as Message],
    })),
  clearMessages: () => set({ messages: [] }),

  // Activities
  activities: [],
  addActivity: (activity) =>
    set((state) => ({
      activities: [...state.activities, { 
        ...activity, 
        id: activity.id || `activity-${Date.now()}-${Math.random().toString(36).substr(2, 9)}` 
      } as AgentActivity],
    })),
  updateActivity: (id, updates) =>
    set((state) => ({
      activities: state.activities.map((a) =>
        a.id === id ? { ...a, ...updates } : a
      ),
    })),
  clearActivities: () => set({ activities: [] }),

  // Streaming
  isStreaming: false,
  setIsStreaming: (isStreaming) => set({ isStreaming }),
  currentStreamingContent: '',
  appendStreamingContent: (content) =>
    set((state) => ({
      currentStreamingContent: state.currentStreamingContent + content,
    })),
  clearStreamingContent: () => set({ currentStreamingContent: '' }),

  // Current agent
  currentAgent: 'orchestrator',
  setCurrentAgent: (currentAgent) => set({ currentAgent }),

  // Input
  inputValue: '',
  setInputValue: (inputValue) => set({ inputValue }),
}));
