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
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  toggleLeft: () => void;
  toggleRight: () => void;
  setRailTab: (t: RailTab) => void;
  setNav: (n: NavKey) => void;
  setMenu: (m: string | null) => void;
  setTier: (t: Tier) => void;
}

export const useShell = create<ShellState>((set) => ({
  theme: "dark",
  leftCollapsed: false,
  rightCollapsed: false,
  railTab: "overview",
  nav: "servers",
  menuOpen: null,
  tier: "requested_approval",
  setTheme: (theme) => set({ theme }),
  toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
  toggleLeft: () => set((s) => ({ leftCollapsed: !s.leftCollapsed })),
  toggleRight: () => set((s) => ({ rightCollapsed: !s.rightCollapsed })),
  setRailTab: (railTab) => set({ railTab }),
  setNav: (nav) => set({ nav }),
  setMenu: (menuOpen) => set({ menuOpen }),
  setTier: (tier) => set({ tier }),
}));
