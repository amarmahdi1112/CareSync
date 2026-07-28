/**
 * UI Store
 * Manages global UI state like modals, sidebars, loading states
 */

import { create } from 'zustand';

interface ConfirmModalState {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  variant: 'danger' | 'warning' | 'primary';
  onConfirm: (() => void) | (() => Promise<void>);
}

interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Global loading overlay
  isLoading: boolean;
  loadingMessage: string;
  setLoading: (loading: boolean, message?: string) => void;

  // Confirm modal
  confirmModal: ConfirmModalState;
  openConfirmModal: (config: Omit<ConfirmModalState, 'isOpen'>) => void;
  closeConfirmModal: () => void;

  // View preferences
  viewMode: 'grid' | 'list';
  setViewMode: (mode: 'grid' | 'list') => void;
}

const initialConfirmModal: ConfirmModalState = {
  isOpen: false,
  title: '',
  message: '',
  confirmLabel: 'Confirm',
  variant: 'primary',
  onConfirm: () => {},
};

export const useUIStore = create<UIState>((set) => ({
  // Sidebar
  sidebarCollapsed: false,
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  // Global loading
  isLoading: false,
  loadingMessage: '',
  setLoading: (loading, message = '') => set({ isLoading: loading, loadingMessage: message }),

  // Confirm modal
  confirmModal: initialConfirmModal,
  openConfirmModal: (config) =>
    set({
      confirmModal: { ...config, isOpen: true },
    }),
  closeConfirmModal: () =>
    set({
      confirmModal: initialConfirmModal,
    }),

  // View preferences
  viewMode: 'grid',
  setViewMode: (mode) => set({ viewMode: mode }),
}));
