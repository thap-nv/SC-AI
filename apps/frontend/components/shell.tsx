"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/providers";
import { LiveDot, Logo, Rule } from "@/components/ui";
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

  if (!user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="flex flex-col items-center gap-3 text-sm text-graphite-500">
          <Logo className="h-10 w-auto text-graphite-900 motion-safe:animate-pulse" />
          Loading…
        </div>
      </div>
    );
  }

  const demo = mode === "DEMO";
  const signOut = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen md:flex">
      <aside className="relative flex flex-col overflow-hidden border-b border-line bg-surface md:sticky md:top-0 md:h-screen md:w-[256px] md:flex-none md:border-b-0 md:border-r">
        <div className="flex items-center gap-3.5 px-[22px] pb-5 pt-6">
          <Logo className="h-[34px] w-auto shrink-0 text-graphite-900" />
          <span className="h-8 w-px bg-line" aria-hidden="true" />
          <div className="font-display text-[14.5px] font-semibold leading-[1.15] text-graphite-900">Safety<br />Monitor</div>
        </div>
        <div className="mx-[22px] h-px bg-line-soft" />
        <div className="eyebrow hidden px-[22px] pb-2 pt-5 text-graphite-400 md:block">Coffee factory</div>
        <nav className="flex gap-0.5 overflow-auto px-3 py-3 md:flex-col md:py-0">
          {LINKS.map((link) => {
            const active = link.href === "/" ? path === "/" : path.startsWith(link.href);
            const badge = link.href === "/incidents" && newCount ? newCount : 0;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`relative flex items-center gap-3 whitespace-nowrap rounded-lg px-3 py-2.5 transition-colors ${active ? "bg-brand-50 text-brand-600" : "text-graphite-600 hover:bg-muted hover:text-graphite-900"}`}
              >
                {active ? <span className="absolute inset-y-2 left-0 hidden w-[3px] rounded-full bg-brand-500 md:block" aria-hidden="true" /> : null}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px] shrink-0" aria-hidden="true">
                  {ICONS[link.icon]}
                </svg>
                <span className={`flex-1 text-[14.5px] ${active ? "font-semibold" : "font-medium"}`}>{link.label}</span>
                {badge ? <span className="min-w-6 rounded-full bg-brand-500 px-[7px] py-0.5 text-center text-[11px] font-bold text-white" aria-label={`${badge} new`}>{badge > 99 ? "99+" : badge}</span> : null}
              </Link>
            );
          })}
        </nav>
        <div className="hidden flex-1 md:block" />
        <div className="flex items-center gap-3 border-t border-line px-[22px] py-4">
          <div className="grid h-[38px] w-[38px] shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand-600">{initials(user.full_name)}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-semibold text-graphite-900" title={user.full_name}>{user.full_name}</div>
            <div className="text-xs capitalize text-graphite-500">{user.role.replace("_", " ").toLowerCase()}</div>
          </div>
          <button onClick={signOut} className="whitespace-nowrap rounded-md border border-line-strong bg-transparent px-2.5 py-1.5 text-xs text-graphite-700 hover:border-brand-500 hover:text-brand-600">
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-[5] flex flex-wrap items-center gap-4 border-b border-line bg-surface/90 px-4 py-3 backdrop-blur md:px-9">
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

        <div className="flex w-full max-w-[1680px] flex-col gap-6 px-4 pb-12 pt-[30px] md:px-9">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex min-w-[260px] flex-1 flex-col gap-1.5">
              <div className="flex items-center gap-3">
                {back ? (
                  <>
                    <Link href={back.href} className="link text-[12.5px]">← {back.label}</Link>
                    <span className="text-graphite-300">/</span>
                  </>
                ) : null}
                <div className="eyebrow text-brand-600">Coffee factory · Safety</div>
              </div>
              <h1 className="m-0 font-display text-[32px] font-bold leading-tight tracking-[-0.01em] text-graphite-900">{title}</h1>
              <p className="text-[14.5px] text-graphite-500">AI raises an alert. A person decides what it means.</p>
            </div>
            {actions ? <div className="flex flex-wrap gap-2.5">{actions}</div> : null}
          </div>
          <Rule className="-mt-2" />
          {children}
        </div>
      </main>
    </div>
  );
}
