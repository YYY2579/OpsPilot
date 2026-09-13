import { create } from "zustand";

export type Theme = "dark" | "light";
export type NavKey = "servers" | "databases" | "projects" | "history" | "starred";
export type RailTab = "overview" | "tools" | "tasks" | "logs";
export type Tier = "requested_approval" | "approve_for_me" | "full_access";

interface ShellState {
  theme: Theme;
  leftCollapsed: boolean;    // 手动收起左栏
  rightCollapsed: boolean;   // 手动收起右栏
  railTab: RailTab;
  nav: NavKey;
  menuOpen: string | null;
  tier: Tier;
  backendOnline: boolean;
  activeServerId: string | null;
  activeTaskId: string | null;
  sessionId: string;
  tierLoading: boolean;
  dialogOpen: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  toggleLeft: () => void;
  toggleRight: () => void;
  setRailTab: (t: RailTab) => void;
  setNav: (n: NavKey) => void;
  setMenu: (m: string | null) => void;
  setTier: (t: Tier) => void;
  setBackendOnline: (v: boolean) => void;
  setActiveServer: (id: string | null) => void;
  setActiveTask: (id: string | null) => void;
  setTierLoading: (v: boolean) => void;
  openDialog: () => void;
  closeDialog: () => void;
}

export const useShell = create<ShellState>((set) => ({
  theme: "dark",
  leftCollapsed: false,
  rightCollapsed: false,
  railTab: "overview",
  nav: "servers",
  menuOpen: null,
  tier: "requested_approval",
  backendOnline: false,
  activeServerId: null,
  activeTaskId: null,
  sessionId: "web-" + Math.random().toString(36).slice(2, 8),
  tierLoading: false,
  dialogOpen: false,
  setTheme: (theme) => set({ theme }),
  toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
  toggleLeft: () => set((s) => ({ leftCollapsed: !s.leftCollapsed })),
  toggleRight: () => set((s) => ({ rightCollapsed: !s.rightCollapsed })),
  setRailTab: (railTab) => set({ railTab }),
  setNav: (nav) => set({ nav }),
  setMenu: (menuOpen) => set({ menuOpen }),
  setTier: (tier) => set({ tier }),
  setBackendOnline: (backendOnline) => set({ backendOnline }),
  setActiveServer: (activeServerId) => set({ activeServerId }),
  setActiveTask: (activeTaskId) => set({ activeTaskId }),
  setTierLoading: (tierLoading) => set({ tierLoading }),
  openDialog: () => set({ dialogOpen: true }),
  closeDialog: () => set({ dialogOpen: false }),
}));
