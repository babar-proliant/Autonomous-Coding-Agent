'use client';

import { Badge } from '@/components/ui/badge';
import { Bot, Zap, Circle, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useChatStore } from '@/stores';
import type { SystemStatus } from '@/types';
import { cn } from '@/lib/utils';

interface FooterProps {
  systemStatus: SystemStatus | null;
}

export function Footer({ systemStatus }: FooterProps) {
  const { currentAgent, isStreaming, activities } = useChatStore();

  // Get tool activity counts
  const toolActivities = activities.filter((a) => a.type.includes('tool'));
  const successCount = toolActivities.filter((a) => a.metadata?.status === 'success').length;
  const failCount = toolActivities.filter((a) => a.metadata?.status === 'failed').length;

  // Determine status display
  const getStatusDisplay = () => {
    if (isStreaming) {
      return {
        text: 'Processing',
        icon: <Loader2 className="h-3 w-3 animate-spin" />,
        color: 'text-amber-500',
        bgColor: 'bg-amber-500/10',
      };
    }
    
    if (systemStatus?.status === 'ready') {
      return {
        text: 'Ready',
        icon: <CheckCircle className="h-3 w-3" />,
        color: 'text-green-500',
        bgColor: 'bg-green-500/10',
      };
    }
    
    if (systemStatus?.status === 'busy') {
      return {
        text: 'Busy',
        icon: <Loader2 className="h-3 w-3 animate-spin" />,
        color: 'text-amber-500',
        bgColor: 'bg-amber-500/10',
      };
    }
    
    return {
      text: 'Offline',
      icon: <XCircle className="h-3 w-3" />,
      color: 'text-red-500',
      bgColor: 'bg-red-500/10',
    };
  };

  const status = getStatusDisplay();

  return (
    <footer className="flex h-8 items-center justify-between border-t border-border bg-muted/30 px-4 text-xs text-muted-foreground">
      {/* Left: Current Agent with Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Bot className="h-3 w-3" />
          <span>Agent:</span>
          <Badge variant="outline" className="h-5 text-xs">
            {"Coder"}
          </Badge>
        </div>
        
        {/* Status Indicator */}
        <div className={cn('flex items-center gap-1.5 rounded-md px-2 py-0.5', status.bgColor)}>
          <span className={status.color}>{status.icon}</span>
          <span className={status.color}>{status.text}</span>
        </div>

        {/* Tool Activity Counts */}
        {(successCount > 0 || failCount > 0) && (
          <div className="flex items-center gap-1">
            {successCount > 0 && (
              <Badge variant="outline" className="h-5 gap-1 bg-green-500/10 text-green-600 text-xs">
                <CheckCircle className="h-3 w-3" />
                {successCount}
              </Badge>
            )}
            {failCount > 0 && (
              <Badge variant="outline" className="h-5 gap-1 bg-red-500/10 text-red-600 text-xs">
                <XCircle className="h-3 w-3" />
                {failCount}
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* Right: Model Info */}
      <div className="flex items-center gap-2">
        <Zap className="h-3 w-3" />
        <span>Model:</span>
        <Badge variant="outline" className="h-5 text-xs">
          {"Qwen-14B"}
        </Badge>
      </div>
    </footer>
  );
}
