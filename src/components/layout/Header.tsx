'use client';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  Moon,
  Sun,
  Settings,
  ChevronDown,
  Cpu,
  HardDrive,
  Bot,
  Zap,
} from 'lucide-react';
import type { Session, SystemStatus } from '@/types';
import { useSettingsStore } from '@/stores/settingsStore';

interface HeaderProps {
  session: Session | null;
  systemStatus: SystemStatus | null;
  onNewSession: () => void;
}

export function Header({ session, systemStatus, onNewSession }: HeaderProps) {
  const { theme, setTheme } = useSettingsStore();

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-background px-4">
      {/* Left: Logo and Session */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Bot className="h-6 w-6 text-primary" />
          <span className="text-sm font-semibold">Autonomous Coding Agent</span>
        </div>
      </div>

      {/* Right: System Stats and Actions */}
      <div className="flex items-center gap-2">
        {/* System Stats */}
        {systemStatus?.system && (
          <div className="hidden items-center gap-3 md:flex">
            <Badge variant="outline" className="gap-1 text-xs">
              <Cpu className="h-3 w-3" />
              {systemStatus.system.cpu_percent.toFixed(0)}%
            </Badge>
            <Badge variant="outline" className="gap-1 text-xs">
              <HardDrive className="h-3 w-3" />
              {systemStatus.system.memory_percent.toFixed(0)}%
            </Badge>
            {systemStatus.models && (
              <Badge variant="outline" className="gap-1 text-xs">
                <Zap className="h-3 w-3" />
                {systemStatus.models.loaded.length} models
              </Badge>
            )}
          </div>
        )}

        <Button variant="ghost" size="sm" onClick={onNewSession}>
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">New Session</span>
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </Button>

      </div>
    </header>
  );
}
