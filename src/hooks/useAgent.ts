/**
 * Custom hook for agent API interactions.
 */

import { useCallback } from 'react';
import { useChatStore } from '@/stores';
import type { Session, ChatResponse, SystemStatus } from '@/types';

const API_BASE = '/api';

export function useAgent() {
  const { setSession, addMessage } = useChatStore();

  // Create a new session
  const createSession = useCallback(
    async (projectName: string = 'New Project'): Promise<Session | null> => {
      try {
        const response = await fetch(`${API_BASE}/session/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_name: projectName,
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to create session');
        }

        const data = await response.json();
        
        const session = {
          ...data,
          id: data.session_id,
        };
        
        setSession(session);
        return session;
      } catch (error) {
        console.error('Error creating session:', error);
        return null;
      }
    },
    [setSession]
  );

  // Send a chat message
  const sendMessage = useCallback(
    async (message: string, sessionId?: string): Promise<ChatResponse | null> => {
      try {
        // Add user message immediately
        addMessage({
          id: `user-${Date.now()}`,
          session_id: sessionId || '',
          role: 'user',
          content: message,
        });

        const response = await fetch(`${API_BASE}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message,
            session_id: sessionId,
          }),
        });

        const data = await response.json();

        if (!response.ok) {
          console.error('Chat error:', data);
          addMessage({
            id: `error-${Date.now()}`,
            session_id: sessionId || '',
            role: 'system',
            content: `Error: ${data.error || 'Failed to send message'}`,
          });
          return null;
        }

        return data;
      } catch (error) {
        console.error('Error sending message:', error);
        addMessage({
          id: `error-${Date.now()}`,
          session_id: sessionId || '',
          role: 'system',
          content: `Error: ${error instanceof Error ? error.message : 'Failed to send message'}`,
        });
        return null;
      }
    },
    [addMessage]
  );

  // Get system status - returns fallback if backend is busy
  const getSystemStatus = useCallback(async (): Promise<SystemStatus | null> => {
    try {
      const response = await fetch(`${API_BASE}/status`);
      
      if (!response.ok) {
        // Return offline status instead of throwing
        return {
          status: 'offline',
          system: {
            cpu_percent: 0,
            memory_percent: 0,
            disk_percent: 0,
          },
          models: {
            loaded: [],
          },
          active_sessions: 0,
        };
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error getting status:', error);
      // Return offline status instead of null
      return {
        status: 'offline',
        system: {
          cpu_percent: 0,
          memory_percent: 0,
          disk_percent: 0,
        },
        models: {
          loaded: [],
        },
        active_sessions: 0,
      };
    }
  }, []);

  // Stop current task
  const stopTask = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/session/${sessionId}/stop`, {
        method: 'POST',
      });
      return response.ok;
    } catch (error) {
      console.error('Error stopping task:', error);
      return false;
    }
  }, []);

  // Get file content
  const getFileContent = useCallback(
    async (sessionId: string, filePath: string): Promise<string | null> => {
      try {
        const response = await fetch(
          `${API_BASE}/file/${sessionId}?path=${encodeURIComponent(filePath)}`
        );
        if (!response.ok) {
          throw new Error('Failed to get file');
        }
        const data = await response.json();
        return data.content;
      } catch (error) {
        console.error('Error getting file:', error);
        return null;
      }
    },
    []
  );

  return {
    createSession,
    sendMessage,
    getSystemStatus,
    stopTask,
    getFileContent,
  };
}
