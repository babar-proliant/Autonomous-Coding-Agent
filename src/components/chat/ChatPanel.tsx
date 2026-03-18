'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useChatStore } from '@/stores';
import { Send, Square, Bot, User, Wrench, ChevronDown, ChevronRight, CheckCircle, XCircle, Clock } from 'lucide-react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import type { AgentActivity } from '@/types';

interface ChatPanelProps {
  onSendMessage: (message: string) => void;
}

export function ChatPanel({ onSendMessage }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const activityScrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages,
    activities,
    isStreaming,
    currentStreamingContent,
  } = useChatStore();

  // Auto-scroll messages to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, currentStreamingContent]);

  // Auto-scroll activities to bottom (show latest)
  useEffect(() => {
    if (activityScrollRef.current) {
      activityScrollRef.current.scrollTop = activityScrollRef.current.scrollHeight;
    }
  }, [activities]);

  const handleSubmit = () => {
    if (input.trim() && !isStreaming) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Get tool activities for counts
  const toolActivities = activities.filter(
    (a) => a.type.includes('tool_') || a.type === 'tool_result' || a.type === 'tool_error'
  );
  const successCount = toolActivities.filter((a) => a.metadata?.status === 'success').length;
  const failCount = toolActivities.filter((a) => a.metadata?.status === 'failed').length;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Messages Area - Scrollable */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4"
      >
        <div className="space-y-4">
          {/* Welcome message if no messages */}
          {messages.length === 0 && activities.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Bot className="mb-4 h-12 w-12 text-muted-foreground" />
              <h2 className="mb-2 text-xl font-semibold">Autonomous Coding Agent</h2>
              <p className="max-w-md text-muted-foreground">
                I can help you build software autonomously. Describe what you want to create,
                and I&apos;ll plan, code, test, and deploy it.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                <Badge variant="outline">Python</Badge>
                <Badge variant="outline">TypeScript</Badge>
                <Badge variant="outline">React</Badge>
                <Badge variant="outline">APIs</Badge>
                <Badge variant="outline">Databases</Badge>
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((message) => (
            <MessageItem key={message.id} message={message} />
          ))}

          {/* Streaming content */}
          {isStreaming && currentStreamingContent && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Bot className="h-4 w-4" />
              </div>
              <div className="max-w-[90%] rounded-lg bg-muted p-3">
                <MarkdownRenderer content={currentStreamingContent} />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Agent Activity Panel - Fixed height, scrollable */}
      {activities.length > 0 && (
        <div className="border-t border-border">
          {/* Header with activity counts */}
          <div className="flex items-center justify-between bg-muted/30 px-3 py-1.5">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Wrench className="h-4 w-4" />
              <span>Agent Activity</span>
              <Badge variant="secondary" className="text-xs">
                {activities.length}
              </Badge>
            </div>
            
            {/* Success/Fail counts */}
            <div className="flex items-center gap-1">
              {successCount > 0 && (
                <Badge variant="outline" className="gap-1 bg-green-500/10 text-green-600 text-xs">
                  <CheckCircle className="h-3 w-3" />
                  {successCount}
                </Badge>
              )}
              {failCount > 0 && (
                <Badge variant="outline" className="gap-1 bg-red-500/10 text-red-600 text-xs">
                  <XCircle className="h-3 w-3" />
                  {failCount}
                </Badge>
              )}
            </div>
          </div>
          
          {/* Scrollable activity list - fixed height for ~1 activity */}
          <ScrollArea className="h-24">
            <div className="space-y-1 p-2" ref={activityScrollRef}>
              {activities.slice(-10).map((activity) => (
                <ActivityItem key={activity.id} activity={activity} />
              ))}
            </div>
          </ScrollArea>
        </div>
      )}

      {/* Input Area - Fixed at Bottom */}
      <div className="shrink-0 border-t border-border bg-background p-4">
        <div className="flex gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe what you want to build..."
            className="min-h-[60px] resize-none"
            disabled={isStreaming}
          />
          <div className="flex flex-col gap-2">
            {isStreaming ? (
              <Button variant="destructive" size="icon">
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button onClick={handleSubmit} size="icon" disabled={!input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Message Item Component
function MessageItem({ message }: { message: { id: string; role: string; content: string; metadata?: Record<string, unknown> } }) {
  const isUser = message.role === 'user';
  const isTool = message.role === 'tool';

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
            isTool
            ? 'bg-orange-500/20 text-orange-600 dark:text-orange-400'
            : 'bg-primary text-primary-foreground'
          }`}
        >
          {isTool ? <Wrench className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
      )}
      
      <div
        className={`max-w-[90%] rounded-lg p-3 ${
          isUser ? 'bg-secondary text-secondary-foreground' : 'bg-muted'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        ) : (
          <MarkdownRenderer content={message.content} />
        )}
      </div>
      
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
          <User className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}

// Activity Item Component
function ActivityItem({ activity }: { activity: AgentActivity }) {
  const [expanded, setExpanded] = useState(false);

  const getIcon = () => {
    if (activity.type.includes('thinking')) return <Bot className="h-4 w-4" />;
    if (activity.type.includes('tool')) {
      const meta = activity.metadata as { status?: string } | undefined;
      if (meta?.status === 'success') return <CheckCircle className="h-4 w-4 text-green-500" />;
      if (meta?.status === 'failed') return <XCircle className="h-4 w-4 text-red-500" />;
      return <Clock className="h-4 w-4 text-amber-500" />;
    }
    if (activity.type === 'error') return <XCircle className="h-4 w-4 text-red-500" />;
    return <span>•</span>;
  };

  return (
    <div className="rounded-md bg-muted/50 p-1.5 text-xs">
      <button
        className="flex w-full items-center gap-2 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
        )}
        {getIcon()}
        <span className="truncate text-muted-foreground flex-1">{activity.content}</span>
        {activity.agent && (
          <Badge variant="outline" className="text-xs">
            {activity.agent}
          </Badge>
        )}
      </button>
      {expanded && activity.metadata && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
          {JSON.stringify(activity.metadata, null, 2)}
        </pre>
      )}
    </div>
  );
}
