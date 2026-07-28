import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ShellState {
  collapsed: boolean;
  mobileOpen: boolean;
  commandOpen: boolean;
  notificationsOpen: boolean;
  toggleCollapsed: () => void;
  setMobileOpen: (open: boolean) => void;
  setCommandOpen: (open: boolean) => void;
  setNotificationsOpen: (open: boolean) => void;
}

export const useShellStore = create<ShellState>()(
  persist(
    (set) => ({
      collapsed: false,
      mobileOpen: false,
      commandOpen: false,
      notificationsOpen: false,
      toggleCollapsed: () => set((state) => ({ collapsed: !state.collapsed })),
      setMobileOpen: (mobileOpen) => set({ mobileOpen }),
      setCommandOpen: (commandOpen) => set({ commandOpen }),
      setNotificationsOpen: (notificationsOpen) => set({ notificationsOpen }),
    }),
    {
      name: 'caresync-redesign-shell-v1',
      partialize: (state) => ({ collapsed: state.collapsed }),
    },
  ),
);
