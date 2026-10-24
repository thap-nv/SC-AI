"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/providers";
import { GhostButton, LiveDot, Logo, Mark, Marker, Rule } from "@/components/ui";
import { API_URL, api, clearSession, getToken, getUser, Incident, User } from "@/lib/api";
import { emitIncident, useIncidentEvents } from "@/lib/live";
import { eventLabel, formatDate, formatTime } from "@/lib/labels";

// 24 × 24 line icons, stroked with currentColor.
const ICONS: Record<string, React.ReactNode> = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>
  ),
  cameras: (
    <>
      <rect x="2.5" y="6" width="13" height="12" rx="2" />
      <path d="M15.5 10.5 21.5 7v10l-6-3.5" />
    </>
  ),
  rules: (
    <>
      <path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h9M17 18h3" />
      <circle cx="15" cy="6" r="2" />
      <circle cx="9" cy="12" r="2" />
      <circle cx="15" cy="18" r="2" />
    </>
  ),
  incidents: (
    <>
      <path d="M10.3 4.2 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9.5v4M12 17h.01" />
    </>
  ),
  evaluation: <path d="M3 20.5h18M6.5 17V11M11.5 17V5.5M16.5 17v-8" />,
};

const LINKS = [
  { href: "/", label: "Overview", icon: "overview" },
  { href: "/cameras", label: "Cameras", icon: "cameras" },
  { href: "/rules", label: "Rules", icon: "rules" },
  { href: "/incidents", label: "Incidents", icon: "incidents" },
  { href: "/evaluation", label: "Evaluation", icon: "evaluation" },
];

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

type ShellProps = {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
};

export default function Shell({ title, children, actions, back }: ShellProps) {
  const router = useRouter();
  const path = usePathname();
  const { toast } = useApp();
  const [user, setUser] = useState<User | null>(null);
  const [mode, setMode] = useState("DEMO");
  const [connected, setConnected] = useState(true);
  const [newCount, setNewCount] = useState(0);
  const [now, setNow] = useState<Date | null>(null);
  const seen = useRef(new Set<string>());

  function loadNewCount() {
    api<{ total: number }>("/api/incidents?status=NEW&limit=1").then((page) => setNewCount(page.total)).catch(() => undefined);
  }

  useEffect(() => {
    const current = getUser();
    if (!current) {
      router.replace("/login");
      return;
    }
    setUser(current);
    api<{ ai_mode: string; worker_connected: boolean }>("/api/system/info")
      .then((info) => {
        setMode(info.ai_mode || "DEMO");
        setConnected(info.worker_connected);
      })
      .catch(() => undefined);
    loadNewCount();
  }, [router, path]);

  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // One stream per page view; every page listens through useIncidentEvents.
  useEffect(() => {
    if (!getToken()) return;
    const source = new EventSource(`${API_URL}/api/events/stream?access_token=${getToken()}`);
    source.onmessage = (message) => {
      try {
        const data = JSON.parse(message.data) as { type?: string; incident?: Incident };
        const incident = data.incident || null;
        emitIncident(incident);
        // A fresh alert arrives NEW and still open; later updates of the same incident do not toast again.
        if (incident && incident.status === "NEW" && !incident.ended_at && !seen.current.has(incident.id)) {
          seen.current.add(incident.id);
          toast(`New alert · ${eventLabel(incident.event_type)}${incident.camera_name ? ` on ${incident.camera_name}` : ""}`, incident.id);
        }
      } catch {
        emitIncident(null);
      }
    };
    return () => source.close();
  }, [toast]);

  useIncidentEvents(loadNewCount, 800);

  // The phone account menu closes on navigation and on Escape.
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [path]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menu]);

  if (!user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="flex flex-col items-center gap-3 text-sm text-graphite-500">
          <Logo light className="text-[16px] motion-safe:animate-pulse" />
          Loading…
        </div>
      </div>
    );
  }

  const demo = mode === "DEMO";
  const modeDetail = `${demo ? "Demonstration labels, not a trained factory model" : "Running the configured detector"}${connected ? "" : " · worker still connecting"}`;
  const role = user.role.replace("_", " ").toLowerCase();
  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  const badgeFor = (href: string) => (href === "/incidents" && newCount ? newCount : 0);
  const signOut = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen md:flex">
      {/* Phone: one slim navy bar with the mark, AI Mode and the account menu; the sections move to the tab bar at the bottom. */}
      <header className="sticky top-0 z-10 flex h-14 items-center gap-2.5 bg-ink px-4 text-fog-100 md:hidden">
        <Link href="/" className="flex min-w-0 items-center gap-2.5">
          <Mark className="h-7" />
          <span className="truncate font-display text-[14.5px] font-semibold text-white min-[380px]:text-[15px]">Safety Monitor</span>
        </Link>
        <div className="flex-1" />
        <span title={modeDetail} className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-1 text-[11px] font-bold min-[380px]:px-2.5 min-[380px]:text-[11.5px] ${demo ? "border-amber-400/40 bg-amber-400/10 text-amber-300" : "border-success-600/40 bg-success-600/15 text-success-200"}`}>
          <LiveDot demo={demo} />
          AI Mode: {mode}
          <span className="sr-only">. {modeDetail}</span>
        </span>
        <div className="relative shrink-0">
          <button onClick={() => setMenu((open) => !open)} aria-expanded={menu} aria-haspopup="menu" aria-label={`Account: ${user.full_name}`} className="grid h-9 w-9 place-items-center rounded-full bg-brand-500/15 p-0 text-xs font-bold text-brand-300">
            {initials(user.full_name)}
          </button>
          {menu ? (
            <>
              <div className="fixed inset-0 z-[11]" onClick={() => setMenu(false)} aria-hidden="true" />
              <div role="menu" className="absolute right-0 top-full z-[12] mt-2 w-60 rounded-xl border border-line bg-surface p-4 text-graphite-800 shadow-[0_14px_40px_rgba(10,21,37,.25)]">
                <div className="truncate text-sm font-semibold text-graphite-900">{user.full_name}</div>
                <div className="text-xs capitalize text-graphite-500">{role}</div>
                <GhostButton role="menuitem" onClick={signOut} className="mt-3.5 w-full">Sign out</GhostButton>
              </div>
            </>
          ) : null}
        </div>
      </header>

      {/* Navy like the site's navigation bar, which is where the cyan logo and gradient wordmark are meant to sit. */}
      <aside className="sticky top-0 hidden h-screen w-[256px] flex-none flex-col overflow-hidden bg-ink bg-glow text-fog-100 md:flex">
        <div className="flex flex-col gap-4 px-[22px] pb-5 pt-6">
          <Logo className="text-[14px]" />
          <div className="flex items-center gap-2 font-display text-[14.5px] font-semibold text-white">
            <Marker />
            Safety Monitor
          </div>
        </div>
        <div className="mx-[22px] h-px bg-white/10" />
        <div className="eyebrow px-[22px] pb-2 pt-5 text-fog-500">Factory & workshop</div>
        <nav className="flex flex-col gap-0.5 overflow-auto px-3">
          {LINKS.map((link) => {
            const active = isActive(link.href);
            const badge = badgeFor(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`relative flex items-center gap-3 whitespace-nowrap rounded-lg px-3 py-2.5 transition-colors ${active ? "bg-white/[0.07] text-brand-300" : "text-fog-300 hover:bg-white/[0.05] hover:text-white"}`}
              >
                {active ? <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-brand-500" aria-hidden="true" /> : null}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px] shrink-0" aria-hidden="true">
                  {ICONS[link.icon]}
                </svg>
                <span className={`flex-1 text-[14.5px] ${active ? "font-semibold" : "font-medium"}`}>{link.label}</span>
                {badge ? <span className="min-w-6 rounded-full bg-brand-500 px-[7px] py-0.5 text-center text-[11px] font-bold text-ink" aria-label={`${badge} new`}>{badge > 99 ? "99+" : badge}</span> : null}
              </Link>
            );
          })}
        </nav>
        <div className="flex-1" />
        <div className="flex items-center gap-3 border-t border-white/10 px-[22px] py-4">
          <div className="grid h-[38px] w-[38px] shrink-0 place-items-center rounded-full bg-brand-500/15 text-xs font-bold text-brand-300">{initials(user.full_name)}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-semibold text-white" title={user.full_name}>{user.full_name}</div>
            <div className="text-xs capitalize text-fog-500">{role}</div>
          </div>
          <button onClick={signOut} className="whitespace-nowrap rounded-md border border-white/15 bg-transparent px-2.5 py-1.5 text-xs text-fog-100 hover:border-brand-500 hover:text-brand-300">
            Sign out
          </button>
        </div>
      </aside>

      {/* On a phone the bottom padding keeps the last card clear of the tab bar. */}
      <main className="flex min-w-0 flex-1 flex-col pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0">
        <header className="sticky top-0 z-[5] hidden flex-wrap items-center gap-4 border-b border-line bg-surface/90 px-9 py-3 backdrop-blur md:flex">
          <div className={`flex items-center gap-2.5 rounded-full border py-1.5 pl-2.5 pr-3 ${demo ? "border-amber-200 bg-amber-50" : "border-success-200 bg-success-50"}`}>
            <LiveDot demo={demo} />
            <span className={`text-[13px] ${demo ? "text-amber-950" : "text-success-900"}`}>
              <strong className="font-bold">AI Mode: {mode}</strong>
              {demo ? " — demonstration labels, not a trained factory model" : " — running the configured detector"}
              {connected ? "" : " · worker still connecting"}
            </span>
          </div>
          <div className="flex-1" />
          {now ? (
            <div className="flex items-center gap-2 font-mono text-[12.5px] text-graphite-500" aria-label="Factory time">
              <span>{formatDate(now)}</span>
              <span className="h-1 w-1 rounded-full bg-brand-500" aria-hidden="true" />
              <span className="font-medium text-graphite-800">{formatTime(now)}</span>
              <span>ICT</span>
            </div>
          ) : null}
        </header>

        <div className="flex w-full max-w-[1680px] flex-col gap-5 px-4 pb-8 pt-5 md:gap-6 md:px-9 md:pb-12 md:pt-[30px]">
          <div className="flex flex-wrap items-end gap-x-4 gap-y-3.5">
            <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-1.5">
              {/* On a phone only the back link stays; the eyebrow and tagline repeat what the top bar already says. */}
              <div className={`items-center gap-3 ${back ? "flex" : "hidden md:flex"}`}>
                {back ? (
                  <>
                    <Link href={back.href} className="link text-[12.5px]">← {back.label}</Link>
                    <span className="hidden text-graphite-300 md:inline">/</span>
                  </>
                ) : null}
                <div className="eyebrow hidden text-brand-600 md:block">Factory · Safety</div>
              </div>
              <h1 className="m-0 font-display text-[26px] font-bold leading-tight tracking-[-0.01em] text-graphite-900 md:text-[32px]">{title}</h1>
              <p className="hidden text-[14.5px] text-graphite-500 md:block">AI raises an alert. A person decides what it means.</p>
            </div>
            {actions ? <div className="flex w-full gap-2.5 sm:w-auto sm:flex-wrap [&>*]:flex-auto [&>*]:whitespace-nowrap sm:[&>*]:flex-none">{actions}</div> : null}
          </div>
          <Rule className="-mt-2" />
          {children}
        </div>
      </main>

      {/* Phone tab bar: the five sections within thumb reach, with the count of new incidents. */}
      <nav aria-label="Sections" className="fixed inset-x-0 bottom-0 z-10 flex border-t border-white/10 bg-ink pb-[env(safe-area-inset-bottom)] md:hidden">
        {LINKS.map((link) => {
          const active = isActive(link.href);
          const badge = badgeFor(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={`relative flex min-w-0 flex-1 flex-col items-center gap-1 pb-2 pt-2.5 text-[10.5px] ${active ? "font-semibold text-brand-300" : "font-medium text-fog-300"}`}
            >
              {active ? <span className="absolute inset-x-[24%] top-0 h-[3px] rounded-b-full bg-brand-500" aria-hidden="true" /> : null}
              <span className="relative">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[22px] w-[22px]" aria-hidden="true">
                  {ICONS[link.icon]}
                </svg>
                {badge ? <span className="absolute -right-3.5 -top-1.5 min-w-[18px] rounded-full bg-brand-500 px-1 text-center text-[10px] font-bold leading-4 text-ink" aria-label={`${badge} new`}>{badge > 99 ? "99+" : badge}</span> : null}
              </span>
              <span className="max-w-full truncate">{link.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
