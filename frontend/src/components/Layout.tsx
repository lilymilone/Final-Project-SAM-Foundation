import {
  Activity,
  CalendarHeart,
  CircleHelp,
  Compass,
  HandCoins,
  HeartHandshake,
  Landmark,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings as SettingsIcon,
  ShieldCheck,
  Sprout,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Logo, Wordmark } from "./Brand";
import { DemoBadge } from "./ui";
import { SirsOffice } from "./SirsOffice";

export const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, group: "" },
  { to: "/events", label: "Event Studio", icon: CalendarHeart, group: "Plan & connect" },
  { to: "/mission", label: "Mission Discovery", icon: Compass, group: "Plan & connect" },
  { to: "/partnerships", label: "Partnerships & Outreach", icon: HeartHandshake, group: "Plan & connect" },
  { to: "/legacy", label: "Our Legacy", icon: Sprout, group: "Records" },
  { to: "/finance", label: "Financial Intelligence", icon: Landmark, group: "Records" },
  { to: "/donations", label: "Donations & Compliance", icon: HandCoins, group: "Records" },
  { to: "/activity", label: "Agent Activity", icon: Activity, group: "Oversight" },
  { to: "/safety", label: "Analytics & Safety", icon: ShieldCheck, group: "Oversight" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, group: "Account" },
  { to: "/help", label: "Help", icon: CircleHelp, group: "Account" },
] as const;

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-4 pb-5 pt-6">
        <Logo size={56} className="!rounded-2xl !p-1" />
        <Wordmark />
      </div>
      <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-2">
        <ul className="space-y-1">
          {NAV.map(({ to, label, icon: Icon, group }, i) => (
            <li key={to}>
              {group && group !== NAV[i - 1]?.group && (
                <p className="mb-1 mt-4 px-3.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-lilac/55">{group}</p>
              )}
              <NavLink
                to={to}
                end={to === "/"}
                onClick={onNavigate}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-xl px-3.5 py-2 text-[0.92rem] font-medium transition-colors ${
                    isActive ? "bg-lilac text-plum shadow-sm" : "text-lilac/85 hover:bg-white/10 hover:text-white"
                  }`
                }
              >
                <Icon size={18} aria-hidden="true" className="shrink-0" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {user && (
        <div className="m-3 rounded-2xl border border-white/10 bg-white/[0.07] p-3.5">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-lavender to-rose font-display text-lg font-semibold text-plum">
              {user.first_name[0]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">
                {user.first_name} {user.last_name}
              </p>
              <p className="truncate text-xs text-lilac/75">{user.title}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-2 text-lilac/80 transition hover:bg-white/10 hover:text-white"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut size={17} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { user } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setDrawerOpen(false), [location.pathname]);
  // Links like /partnerships#draft-56 scroll to that item once the page has loaded it, and highlight it briefly.
  useEffect(() => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    let tries = 0;
    let timer: number | undefined;
    const find = () => {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        el.classList.add("target-flash");
        timer = window.setTimeout(() => el.classList.remove("target-flash"), 2200);
      } else if (tries++ < 40) timer = window.setTimeout(find, 100);
    };
    find();
    return () => window.clearTimeout(timer);
  }, [location.pathname, location.hash]);
  const current = NAV.find((n) => (n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to)));

  return (
    <div className="app-backdrop min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2">
        Skip to content
      </a>
      {/* desktop sidebar */}
      <aside className="sidebar-surface fixed inset-y-0 left-0 z-30 hidden w-72 lg:block">
        <SidebarContent />
      </aside>

      {/* tablet / small-screen top bar + drawer */}
      <div className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-lavender/30 bg-ivory/85 px-4 py-3 backdrop-blur lg:hidden">
        <button className="btn btn-soft !px-3 !py-2" onClick={() => setDrawerOpen(true)} aria-label="Open menu" aria-expanded={drawerOpen}>
          <Menu size={18} aria-hidden="true" />
        </button>
        <span className="wordmark text-lg text-plum">SAM SPACE</span>
        <span className="w-10" />
      </div>
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button className="absolute inset-0 bg-plum/40 backdrop-blur-sm" onClick={() => setDrawerOpen(false)} aria-label="Close menu" />
          <aside className="sidebar-surface relative h-full w-72 max-w-[85vw] shadow-2xl">
            <button
              className="absolute right-3 top-3 z-10 rounded-lg p-2 text-lilac hover:bg-white/10"
              onClick={() => setDrawerOpen(false)}
              aria-label="Close menu"
            >
              <X size={18} aria-hidden="true" />
            </button>
            <SidebarContent onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <div className="lg:pl-72">
        {user?.is_demo && (
          <div className="border-b border-rose/25 bg-blush/50 px-6 py-2 text-center text-[0.8rem] text-plum">
            <DemoBadge label="Demo mode" />{" "}
            <span className="ml-1">You're signed in to a demonstration workspace. All records marked "Demo" are synthetic.</span>
          </div>
        )}
        <main id="main" className="mx-auto max-w-6xl px-4 pb-28 pt-8 sm:px-8 lg:pt-10" aria-label={current?.label}>
          <Outlet />
        </main>
        <SirsOffice />
      </div>
    </div>
  );
}
