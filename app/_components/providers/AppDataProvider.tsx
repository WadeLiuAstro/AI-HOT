// 全局应用状态：当前视图 + 侧栏开合 + URL hash 同步
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { ViewKey } from "../../_lib/types";

const VALID_VIEWS: ViewKey[] = ["featured", "hot", "all", "daily"];

interface AppState {
  view: ViewKey;
  setView: (v: ViewKey) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
}

const AppContext = createContext<AppState | null>(null);

function viewFromHash(): ViewKey {
  if (typeof window === "undefined") return "featured";
  const h = window.location.hash.replace(/^#\/?/, "") as ViewKey;
  return VALID_VIEWS.includes(h) ? h : "featured";
}

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [view, setViewRaw] = useState<ViewKey>("featured");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // 挂载时读取 hash，并监听浏览器前进/后退
  useEffect(() => {
    setViewRaw(viewFromHash());
    const onHashChange = () => setViewRaw(viewFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const setView = useCallback((v: ViewKey) => {
    setViewRaw(v);
    setSidebarOpen(false);
    if (typeof window !== "undefined") {
      const target = `#/${v}`;
      if (window.location.hash !== target) {
        window.history.pushState(null, "", target);
      }
    }
  }, []);

  return (
    <AppContext.Provider value={{ view, setView, sidebarOpen, setSidebarOpen }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp 必须在 AppDataProvider 内使用");
  return ctx;
}
