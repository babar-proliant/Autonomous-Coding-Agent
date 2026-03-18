/**
 * Custom hook for SSE streaming.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useChatStore } from '@/stores';
import type { AgentEvent, EventType } from '@/types';

interface UseSSEOptions {
  sessionId: string | null;
  onEvent?: (event: AgentEvent) => void;
  onError?: (error: Error) => void;
}

const BACKEND_PORT = '8000';

export function useSSE({ sessionId, onEvent, onError }: UseSSEOptions) {
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isIntentionalDisconnectRef = useRef(false);
  const isConnectingRef = useRef(false);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const connectionPromiseRef = useRef<{ resolve: () => void } | null>(null);

  const {
    addActivity,
    setIsStreaming,
    appendStreamingContent,
    clearStreamingContent,
    addMessage,
    setCurrentAgent,
  } = useChatStore();

  // Handle event message
  const handleEventMessage = useCallback((type: EventType, data: Record<string, unknown>) => {
    const event: AgentEvent = {
      event_type: type,
      session_id: sessionId || '',
      data,
      timestamp: new Date().toISOString(),
    };

    onEvent?.(event);

    switch (type) {
      case 'connected':
        console.log('SSE: Connected to event stream');
        // Resolve any pending connection promise
        if (connectionPromiseRef.current) {
          connectionPromiseRef.current.resolve();
          connectionPromiseRef.current = null;
        }
        break;

      case 'thinking_start':
        setIsStreaming(true);
        clearStreamingContent();
        if (data.agent) {
          setCurrentAgent(data.agent as string);
        }
        addActivity({
          type,
          agent: data.agent as string,
          content: (data.message as string) || 'Thinking...',
          timestamp: new Date(),
          expanded: false,
        });
        break;

      case 'thinking_stream':
        if (data.content) {
          appendStreamingContent(data.content as string);
        }
        break;

      case 'thinking_end':
        setIsStreaming(false);
        // Add the final message if we have content
        if (data.content) {
          addMessage({
            session_id: sessionId || '',
            role: 'agent',
            content: data.content as string,
            metadata: data.metadata as Record<string, unknown>,
          });
        }
        // Always clear streaming content after adding message
        clearStreamingContent();
        break;

      case 'tool_start':
        addActivity({
          type,
          agent: data.agent as string,
          content: `Using tool: ${data.tool_name || 'unknown'}`,
          timestamp: new Date(),
          expanded: false,
          metadata: data,
        });
        break;

      case 'tool_result':
      case 'tool_output':
        addActivity({
          type,
          content: `Tool: ${(data.result as string)?.slice(0, 100) || data.status || 'completed'}`,
          timestamp: new Date(),
          expanded: false,
          metadata: data,
        });
        break;

      case 'agent_switch':
        if (data.to_agent) {
          setCurrentAgent(data.to_agent as string);
        }
        addActivity({
          type,
          content: `Switched to ${data.to_agent || 'agent'}`,
          timestamp: new Date(),
          expanded: false,
          metadata: data,
        });
        break;

      case 'error':
        addActivity({
          type,
          content: `Error: ${data.error || 'Unknown error'}`,
          timestamp: new Date(),
          expanded: true,
          metadata: data,
        });
        break;

      case 'done':
        setIsStreaming(false);
        break;

      default:
        if (Object.keys(data).length > 0) {
          addActivity({
            type,
            content: JSON.stringify(data).slice(0, 200),
            timestamp: new Date(),
            expanded: false,
            metadata: data,
          });
        }
    }
  }, [
    sessionId,
    onEvent,
    addActivity,
    setIsStreaming,
    appendStreamingContent,
    clearStreamingContent,
    addMessage,
    setCurrentAgent,
  ]);

  // Disconnect function
  const disconnect = useCallback(() => {
    isIntentionalDisconnectRef.current = true;
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setConnectionStatus('disconnected');
  }, []);

  // Connect function - defined as a ref to avoid circular dependency
  const connectRef = useRef<() => void>(() => {});

  // Update connect ref
  useEffect(() => {
    connectRef.current = async () => {
      if (!sessionId || isConnectingRef.current) {
        return;
      }

      isConnectingRef.current = true;
      isIntentionalDisconnectRef.current = false;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const url = `http://localhost:${BACKEND_PORT}/api/events/${sessionId}`;
      console.log('SSE connecting to:', url);
      setConnectionStatus('connecting');

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: {
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache',
          },
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        console.log('SSE connection opened for session:', sessionId);
        setConnectionStatus('connected');
        
        // Resolve any pending connection promise
        if (connectionPromiseRef.current) {
          connectionPromiseRef.current.resolve();
          connectionPromiseRef.current = null;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            console.log('SSE stream completed (backend closed stream)');
            break;
          }

          buffer += decoder.decode(value, { stream: true });

          const events = buffer.split('\n\n');
          buffer = events.pop() || '';

          for (const eventStr of events) {
            if (!eventStr.trim()) continue;

            const lines = eventStr.split('\n');
            let eventType: string | null = null;
            let eventData: string | null = null;

            for (const line of lines) {
              if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith('data:')) {
                eventData = line.slice(5).trim();
              }
            }

            if (eventType && eventData) {
              try {
                const data = JSON.parse(eventData);
                handleEventMessage(eventType as EventType, data);
              } catch (e) {
                console.error('Failed to parse event data:', eventData, e);
              }
            }
          }
        }

        setConnectionStatus('disconnected');

        // Reconnect if not intentional disconnect
        if (!isIntentionalDisconnectRef.current && sessionId) {
          console.log('SSE: Stream ended, reconnecting in 500ms...');
          reconnectTimeoutRef.current = setTimeout(() => {
            isConnectingRef.current = false;
            connectRef.current();
          }, 500);
        }
      } catch (error: unknown) {
        const err = error as Error;
        if (err.name === 'AbortError') {
          console.log('SSE connection aborted');
          isConnectingRef.current = false;
          return;
        }

        console.error('SSE connection error:', error);
        setConnectionStatus('error');

        if (!isIntentionalDisconnectRef.current && sessionId) {
          reconnectTimeoutRef.current = setTimeout(() => {
            isConnectingRef.current = false;
            connectRef.current();
          }, 3000);
        }

        onError?.(err);
      }
    };
  }, [sessionId, handleEventMessage, onError]);

  // Wait for connection to be established
  const waitForConnection = useCallback((timeout: number = 5000): Promise<boolean> => {
    return new Promise((resolve) => {
      if (connectionStatus === 'connected') {
        resolve(true);
        return;
      }
      
      const timeoutId = setTimeout(() => {
        resolve(false);
      }, timeout);
      
      connectionPromiseRef.current = {
        resolve: () => {
          clearTimeout(timeoutId);
          resolve(true);
        }
      };
    });
  }, [connectionStatus]);

  // Connect on mount or sessionId change
  useEffect(() => {
    if (!sessionId) {
      disconnect();
      return;
    }

    isConnectingRef.current = false;
    connectRef.current();

    return () => {
      disconnect();
    };
  }, [sessionId, disconnect]);

  return { 
    connect: () => connectRef.current(), 
    disconnect, 
    connectionStatus,
    waitForConnection,
  };
}
