'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Wrench,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
  Clock,
  X,
} from 'lucide-react';
import { useChatStore } from '@/stores';

interface ToolMetadata {
  tool_name?: string;
  status?: 'pending' | 'success' | 'failed';
  args?: Record<string, unknown>;
  result?: unknown;
  error?: string;
}

export function ToolOutput() {
  const { activities } = useChatStore();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [isHidden, setIsHidden] = useState(false);

  // Filter tool activities
  const toolActivities = activities.filter(
    (a) => a.type.includes('tool_') || a.type === 'tool_result' || a.type === 'tool_error'
  );

  if (isHidden || toolActivities.length === 0) {
    return null;
  }

  const toggleItem = (id: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const successCount = toolActivities.filter((a) => (a.metadata as ToolMetadata)?.status === 'success').length;
  const failCount = toolActivities.filter((a) => (a.metadata as ToolMetadata)?.status === 'failed').length;

  // Helper to safely get metadata
  const getMetadata = (activity: typeof toolActivities[0]): ToolMetadata => {
    return (activity.metadata as ToolMetadata) || {};
  };

  return (
    <div className="border-t border-border">
      {/* Header */}
      <div className="flex items-center justify-between bg-muted/30 px-3 py-2">
        <button
          className="flex items-center gap-2 text-sm font-medium"
          onClick={() => setIsCollapsed(!isCollapsed)}
        >
          <Wrench className="h-4 w-4" />
          <span>Tool Output</span>
          <Badge variant="secondary" className="ml-1">
            {toolActivities.length}
          </Badge>
          {successCount > 0 && (
            <Badge variant="outline" className="bg-green-500/10 text-green-600 border-green-200">
              {successCount} ✓
            </Badge>
          )}
          {failCount > 0 && (
            <Badge variant="outline" className="bg-red-500/10 text-red-600 border-red-200">
              {failCount} ✗
            </Badge>
          )}
        </button>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => setExpandedItems(new Set())}
          >
            Collapse All
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2"
            onClick={() => setIsHidden(true)}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Content */}
      {!isCollapsed && (
        <ScrollArea className="max-h-48">
          <div className="space-y-1 p-2">
            {toolActivities.map((activity) => {
              const isExpanded = expandedItems.has(activity.id);
              const meta = getMetadata(activity);
              const isSuccess = meta.status === 'success';
              const isFailed = meta.status === 'failed';

              return (
                <Collapsible
                  key={activity.id}
                  open={isExpanded}
                  onOpenChange={() => toggleItem(activity.id)}
                >
                  <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md bg-muted/30 px-2 py-1.5 text-sm hover:bg-muted/50">
                    {isExpanded ? (
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="h-3 w-3 text-muted-foreground" />
                    )}
                    
                    {isSuccess && <CheckCircle className="h-4 w-4 text-green-500" />}
                    {isFailed && <XCircle className="h-4 w-4 text-red-500" />}
                    {!isSuccess && !isFailed && <Clock className="h-4 w-4 text-amber-500" />}
                    
                    <span className="font-mono text-xs">
                      {meta.tool_name || 'tool'}
                    </span>
                    
                    {activity.agent && (
                      <Badge variant="outline" className="ml-auto text-xs">
                        {activity.agent}
                      </Badge>
                    )}
                  </CollapsibleTrigger>
                  
                  <CollapsibleContent>
                    <div className="mt-1 rounded-md bg-muted/20 p-2 text-xs">
                      {meta.args && (
                        <div className="mb-2">
                          <span className="text-muted-foreground">Input: </span>
                          <code className="text-primary">
                            {JSON.stringify(meta.args).slice(0, 100)}
                            {JSON.stringify(meta.args).length > 100 && '...'}
                          </code>
                        </div>
                      )}
                      
                      {meta.result !== undefined && meta.result !== null && (
                        <div className="mb-2">
                          <span className="text-muted-foreground">Result: </span>
                          <code className="text-green-600 dark:text-green-400">
                            {(() => {
                              const resultStr = typeof meta.result === 'string'
                                ? meta.result
                                : JSON.stringify(meta.result);
                              return resultStr.slice(0, 150) + (resultStr.length > 150 ? '...' : '');
                            })()}
                          </code>
                        </div>
                      )}
                      
                      {meta.error && (
                        <div>
                          <span className="text-muted-foreground">Error: </span>
                          <code className="text-red-600 dark:text-red-400">
                            {meta.error}
                          </code>
                        </div>
                      )}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              );
            })}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
