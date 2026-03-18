'use client';

import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';
import { useChatStore } from '@/stores';

export function TaskPanel() {
  const { activities, isStreaming, currentAgent } = useChatStore();

  // Get task-related activities
  const taskActivities = activities.filter(
    (a) => a.type.includes('task') || a.type.includes('thinking')
  );

  // Count successes and failures from tool activities
  const toolActivities = activities.filter((a) => a.type.includes('tool'));
  const successCount = toolActivities.filter(
    (a) => a.metadata?.status === 'success'
  ).length;
  const failCount = toolActivities.filter(
    (a) => a.metadata?.status === 'failed'
  ).length;

  if (taskActivities.length === 0 && !isStreaming) {
    return null;
  }

  return (
    <div className="flex items-center gap-3 border-b border-border bg-muted/20 px-4 py-2">
      {isStreaming ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          <span className="text-sm">
            {currentAgent === 'coder' ? 'Writing code...' :
             currentAgent === 'planner' ? 'Planning...' :
             currentAgent === 'reviewer' ? 'Reviewing...' :
             currentAgent === 'debugger' ? 'Debugging...' :
             'Processing...'}
          </span>
        </>
      ) : (
        <>
          <CheckCircle className="h-4 w-4 text-green-500" />
          <span className="text-sm">Ready</span>
        </>
      )}

      <div className="ml-auto flex items-center gap-2">
        {successCount > 0 && (
          <Badge variant="outline" className="gap-1 bg-green-500/10 text-green-600">
            <CheckCircle className="h-3 w-3" />
            {successCount}
          </Badge>
        )}
        {failCount > 0 && (
          <Badge variant="outline" className="gap-1 bg-red-500/10 text-red-600">
            <XCircle className="h-3 w-3" />
            {failCount}
          </Badge>
        )}
      </div>
    </div>
  );
}
