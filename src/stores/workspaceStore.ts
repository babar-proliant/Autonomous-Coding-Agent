/**
 * Zustand store for workspace state management.
 */

import { create } from 'zustand';
import type { FileEntry, Tab } from '@/types';

interface WorkspaceState {
  // Files
  files: FileEntry[];
  setFiles: (files: FileEntry[]) => void;
  currentPath: string;
  setCurrentPath: (path: string) => void;

  // Selected file
  selectedFile: FileEntry | null;
  setSelectedFile: (file: FileEntry | null) => void;

  // Tabs
  tabs: Tab[];
  activeTabId: string | null;
  openTab: (tab: Omit<Tab, 'id' | 'isActive'>) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  updateTabContent: (id: string, content: string) => void;
  closeAllTabs: () => void;

  // Panel state
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
  isSidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // Loading state
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  // Files
  files: [],
  setFiles: (files) => set({ files }),
  currentPath: '',
  setCurrentPath: (currentPath) => set({ currentPath }),

  // Selected file
  selectedFile: null,
  setSelectedFile: (selectedFile) => set({ selectedFile }),

  // Tabs
  tabs: [],
  activeTabId: null,
  openTab: (tab) =>
    set((state) => {
      const id = `${tab.type}-${tab.path || tab.name}`;
      const existingTab = state.tabs.find((t) => t.id === id);

      if (existingTab) {
        return {
          tabs: state.tabs.map((t) => ({
            ...t,
            isActive: t.id === id,
          })),
          activeTabId: id,
        };
      }

      const newTab: Tab = {
        ...tab,
        id,
        isActive: true,
      };

      return {
        tabs: [...state.tabs.map((t) => ({ ...t, isActive: false })), newTab],
        activeTabId: id,
      };
    }),
  closeTab: (id) =>
    set((state) => {
      const tabIndex = state.tabs.findIndex((t) => t.id === id);
      const newTabs = state.tabs.filter((t) => t.id !== id);

      if (state.activeTabId === id && newTabs.length > 0) {
        const newActiveIndex = Math.min(tabIndex, newTabs.length - 1);
        newTabs[newActiveIndex].isActive = true;
        return {
          tabs: newTabs,
          activeTabId: newTabs[newActiveIndex].id,
        };
      }

      return {
        tabs: newTabs,
        activeTabId: newTabs.length > 0 ? newTabs[0]?.id : null,
      };
    }),
  setActiveTab: (id) =>
    set((state) => ({
      tabs: state.tabs.map((t) => ({
        ...t,
        isActive: t.id === id,
      })),
      activeTabId: id,
    })),
  updateTabContent: (id, content) =>
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === id ? { ...t, content } : t)),
    })),
  closeAllTabs: () => set({ tabs: [], activeTabId: null }),

  // Panel state
  sidebarWidth: 300,
  setSidebarWidth: (sidebarWidth) => set({ sidebarWidth }),
  isSidebarCollapsed: false,
  toggleSidebar: () =>
    set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),

  // Loading state
  isLoading: false,
  setIsLoading: (isLoading) => set({ isLoading }),
}));
