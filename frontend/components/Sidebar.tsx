"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart2, TrendingUp, BookOpen, Users, Globe, Beaker,
  Home, Star, ShieldCheck, FileText, LineChart, LogOut,
  ChevronLeft, ChevronRight, Cpu,
} from "lucide-react";
import { getUser, logout } from "@/lib/auth";
import type { AuthUser } from "@/lib/auth";

const API_ROOT = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace("/api", "");

const NAV = [
  { href: "/",                       label: "Dashboard",        icon: Home },
  { href: "/scanner",                label: "Scanner",          icon: BarChart2 },
  { href: "/watchlist",              label: "Watchlist",        icon: Star },
  { href: "/longterm",               label: "Long Term",        icon: LineChart },
  { href: "/trades",                 label: "Trades",           icon: TrendingUp },
  { href: "/strategy",               label: "Strategy",         icon: FileText },
  { href: "/journal",                label: "Journal",          icon: BookOpen },
  { href: "/influencers",            label: "Influencers",      icon: Users },
  { href: "/politics",               label: "Politics",         icon: Globe },
  { href: "/backtest",               label: "Backtest",         icon: Beaker },
  { href: "/admin/circuit-breakers", label: "Circuit Breakers", icon: ShieldCheck },
  { href: "/admin/ai-costs",         label: "AI Costs",         icon: Cpu },
];

export function Sidebar() {
  const path = usePathname();
  const [backendUp, setBackendUp]   = useState<boolean | null>(null);
  const [user, setUser]             = useState<AuthUser | null>(null);
  const [collapsed, setCollapsed]   = useState(false);

  useEffect(() => {
    setUser(getUser());
    const saved = localStorage.getItem("sidebar_collapsed");
    if (saved !== null) setCollapsed(saved === "true");
  }, []);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar_collapsed", String(next));
  };

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${API_ROOT}/health`, { signal: AbortSignal.timeout(3000) });
        setBackendUp(r.ok);
      } catch { setBackendUp(false); }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <aside className={`${collapsed ? "w-12" : "w-44"} bg-gray-950 border-r border-gray-800/60 flex flex-col py-3 flex-shrink-0 transition-all duration-150`}>

      {/* Logo */}
      <div className={`px-3 mb-4 ${collapsed ? "text-center" : ""}`}>
        {collapsed ? (
          <span className="text-green-400 text-base">⚡</span>
        ) : (
          <>
            <div className="text-green-400 font-semibold text-sm tracking-tight">⚡ Trade Bot</div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                backendUp === null ? "bg-gray-700" :
                backendUp ? "bg-green-500" : "bg-red-500 animate-pulse"
              }`} />
              <span className="text-gray-700 text-[10px]">
                {backendUp === null ? "checking" : backendUp ? "online" : "offline"}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-1.5 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={`flex items-center gap-2.5 px-2 py-1.5 rounded text-xs font-medium transition ${
                active
                  ? "bg-green-900/25 text-green-400"
                  : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
              } ${collapsed ? "justify-center" : ""}`}
            >
              <Icon className="w-3.5 h-3.5 flex-shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className={`px-2 pt-2 border-t border-gray-800/60 mt-1 space-y-1 ${collapsed ? "flex flex-col items-center" : ""}`}>
        {/* User + logout */}
        {user && !collapsed && (
          <div className="flex items-center justify-between px-1">
            <span className="text-gray-600 text-[10px]">{user.display_name}</span>
            <button onClick={logout} title="Sign out" className="text-gray-700 hover:text-red-400 transition p-0.5">
              <LogOut className="w-3 h-3" />
            </button>
          </div>
        )}
        {user && collapsed && (
          <button onClick={logout} title="Sign out" className="text-gray-700 hover:text-red-400 transition p-1">
            <LogOut className="w-3 h-3" />
          </button>
        )}

        {/* Collapse toggle */}
        <button
          onClick={toggle}
          className={`flex items-center gap-1.5 px-1 py-1 text-gray-700 hover:text-gray-400 transition text-[10px] w-full ${collapsed ? "justify-center" : ""}`}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed
            ? <ChevronRight className="w-3 h-3" />
            : <><ChevronLeft className="w-3 h-3" /><span>Collapse</span></>
          }
        </button>
      </div>
    </aside>
  );
}
