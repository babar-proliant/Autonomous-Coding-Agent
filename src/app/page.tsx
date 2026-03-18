'use client';

import { useState, useEffect, useCallback } from 'react';
import { useChatStore } from '@/stores';
import { useSSE } from '@/hooks/useSSE';
import { useAgent } from '@/hooks/useAgent';
import { Header } from '@/components/layout/Header';
import { Footer } from '@/components/layout/Footer';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { WorkspacePanel } from '@/components/workspace/WorkspacePanel';
import type { SystemStatus } from '@/types';

export default function Home() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

  const { session } = useChatStore();
  const { createSession, getSystemStatus, sendMessage } = useAgent();

  // SSE connection for real-time updates
  const { waitForConnection } = useSSE({
    sessionId: session?.id || null,
    onError: (error) => {
      console.error('SSE error:', error);
    },
  });

  // Initialize session and fetch status
  useEffect(() => {
    const init = async () => {
      // Create session on page load so SSE can connect early
      if (!session) {
        await createSession('New Project');
      }
      
      const status = await getSystemStatus();
      if (status) {
        setSystemStatus(status);
      }
    };

    init();

    // Poll status every 15 seconds
    const interval = setInterval(async () => {
      const status = await getSystemStatus();
      if (status) {
        setSystemStatus(status);
      }
    }, 15000);

    return () => clearInterval(interval);
  }, [getSystemStatus, createSession, session]);

  // Handle new session creation
  const handleNewSession = useCallback(async () => {
    await createSession('New Project');
  }, [createSession]);

  // Handle sending messages
  const handleSendMessage = useCallback(
    async (message: string) => {
      let targetSession = session;
      
      // Create session if needed
      if (!targetSession) {
        targetSession = await createSession();
      }
      
      // Wait for SSE to be connected before sending
      if (targetSession) {
        const connected = await waitForConnection(3000);
        if (!connected) {
          console.warn('SSE not connected, message may be missed');
        }
        await sendMessage(message, targetSession.id);
      }
    },
    [session, createSession, sendMessage, waitForConnection]
  );

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      {/* Header */}
      <Header
        session={session}
        systemStatus={systemStatus}
        onNewSession={handleNewSession}
      />

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - Chat */}
        <div className="flex w-1/2 min-w-[400px] flex-col border-r border-border">
          {/* Chat Panel (includes Task Status) */}
          <ChatPanel onSendMessage={handleSendMessage} />
        </div>

        {/* Right Panel - Workspace */}
        <div className="flex w-1/2 min-w-[400px] flex-col">
          {/* Workspace Panel - File Tree & Code Preview */}
          <WorkspacePanel 
            sessionId={session?.id || null}
            onRefresh={() => {/* Refresh handled internally */}}
            onNewSession={handleNewSession}
          />
        </div>
      </div>

      {/* Footer */}
      <Footer systemStatus={systemStatus} />
    </div>
  );
}
