"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/providers";
import Shell from "@/components/shell";
import { Badge, Checkbox, Drawer, ErrorText, GhostButton, Notice, OutlineButton, PrimaryButton, RecDot, SeverityTag, StatusPill, Switch } from "@/components/ui";
import { api, Camera, getUser, imageUrl, Incident, Rule } from "@/lib/api";
import { useIncidentEvents } from "@/lib/live";
import { eventLabel, formatTime } from "@/lib/labels";

// item is helmet, clothing, shoes, mask, zone for a zone breach, or step1 to step6 for a WHO hand-washing step.
type Check = { item?: string; text: string; state: "violation" | "ok" | "unknown" };

const ITEM_NAMES: Record<string, string> = { helmet: "Helmet", clothing: "Clothing", shoes: "Shoes", mask: "Mask" };
const CHECK_CHIPS: Record<Check["state"], { mark: string; style: string }> = {
  violation: { mark: "✗", style: "bg-danger-500/25 text-danger-200" },
  ok: { mark: "✓", style: "bg-success-600/20 text-success-200" },
  unknown: { mark: "?", style: "bg-ink-edge text-fog-300" },
};

type ZoneState = { id: string; name: string; state: string; shift_pct: number };

const ZONE_STATES: Record<string, { label: (zone: ZoneState) => string; tone: string }> = {
  ALIGNED: { label: () => "On · view matches", tone: "green" },
  SHIFTED: { label: (zone) => `On · moved with camera (${zone.shift_pct}%)`, tone: "blue" },
  VIEW_CHANGED: { label: () => "Paused · camera view changed", tone: "red" },
  OUT_OF_VIEW: { label: () => "Paused · out of view", tone: "red" },
  UNVERIFIED: { label: () => "On · not linked to a view", tone: "slate" },
  OTHER_VIEW: { label: () => "Hidden · another view is active", tone: "slate" },
};

const PAUSED_STATES = new Set(["VIEW_CHANGED", "OUT_OF_VIEW"]);
const LIVE = new Set(["ONLINE", "AI_PROCESSING"]);

// ppe: helmet, clothing, shoes, mask → YES | NO | UNKNOWN
// vehicle_type for a vehicle: car, truck, bus, motorcycle or forklift.
// class_name hands is a wash under way at a sink; wash_s is how long the hands have been washing.
type Track = { track_id: string; class_name: string; confidence: number; ppe?: Record<string, string>; vehicle_type?: string | null; checks?: Check[]; wash_s?: number | null };

type Live = {
  status: string;
  ai_mode?: string;
  ai_fps?: number;
  inference_ms?: number;
  frames_processed?: number;
  dropped_frames?: number;
  source_state?: string;
  tracks: Track[];
  zones?: ZoneState[];
};

// How a tracked person or vehicle reads in the "In view" card.
function verdict(track: Track) {
  const checks = track.checks || [];
  if (checks.some((check) => check.state === "violation")) return { chip: "Violation", box: "border-danger-500", style: "bg-danger-500/20 text-danger-200" };
  const hands = track.class_name === "hands";
  if (checks.length && checks.every((check) => check.state === "ok")) return { chip: hands ? "All steps done" : track.class_name === "person" ? "Compliant" : "Allowed", box: "border-success-600", style: "bg-success-600/20 text-success-200" };
  return { chip: hands ? "Washing" : "Not checked", box: "border-fog-500", style: "bg-ink-edge text-fog-300" };
}

function trackName(track: Track) {
  if (track.class_name === "person") return `Person ${track.track_id}`;
  if (track.class_name === "hands") return `Hand wash · ${track.wash_s ?? 0}s`;
  return `${vehicleName(track.vehicle_type)} ${track.track_id}`;
}

function vehicleName(type?: string | null) {
  return type ? type.charAt(0).toUpperCase() + type.slice(1) : "Vehicle";
}

export default function CameraDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { toast, openIncident } = useApp();
  const [camera, setCamera] = useState<Camera | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [frame, setFrame] = useState("");
  const [overlay, setOverlay] = useState(true);
  const [recent, setRecent] = useState<Incident[]>([]);
  const [ruleCount, setRuleCount] = useState(0);
  const [now, setNow] = useState<Date | null>(null);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [message, setMessage] = useState("");
  const [role, setRole] = useState("");
  const [fpsDraft, setFpsDraft] = useState<number | null>(null);
  const [upload, setUpload] = useState("");
  const [canFullscreen, setCanFullscreen] = useState(false);
  const [toggling, setToggling] = useState(false);
  const fpsTimer = useRef<ReturnType<typeof setTimeout>>();
  const stage = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setRole(getUser()?.role || "");
    setCanFullscreen(Boolean(document.fullscreenEnabled));
  }, []);
  useEffect(() => {
    if (camera) setFpsDraft(camera.ai_fps);
  }, [camera?.id, camera?.ai_fps]);
  const canReview = role === "ADMIN" || role === "SAFETY_MANAGER";
  const admin = role === "ADMIN";

  async function loadFrame(showOverlay: boolean) {
    try {
      const url = await imageUrl(`/api/cameras/${params.id}/snapshot${showOverlay ? "" : "?raw=true"}`);
      setFrame((current) => {
        if (current) URL.revokeObjectURL(current);
        return url;
      });
    } catch {
      setFrame((current) => {
        if (current) URL.revokeObjectURL(current);
        return "";
      });
    }
  }

  function loadRecent() {
    api<{ items: Incident[] }>(`/api/incidents?camera_id=${params.id}&limit=4`).then((page) => setRecent(page.items)).catch(() => undefined);
  }

  useEffect(() => {
    loadRecent();
    api<Rule[]>("/api/rules").then((rules) => setRuleCount(rules.filter((rule) => rule.camera_id === params.id).length)).catch(() => undefined);
    setNow(new Date());
    const clock = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(clock);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);
  useIncidentEvents(loadRecent, 800);

  useEffect(() => {
    api<Camera>(`/api/cameras/${params.id}`).then(setCamera).catch((err) => setError(err.message));
    const target = Math.min(10, Math.max(1, camera?.ai_fps || 25));
    let frameBusy = false;
    const tickLive = () => {
      api<Live>(`/api/cameras/${params.id}/live`).then(setLive).catch(() => undefined);
    };
    const tickFrame = () => {
      if (frameBusy) return;
      frameBusy = true;
      loadFrame(overlay).finally(() => {
        frameBusy = false;
      });
    };
    tickLive();
    tickFrame();
    const liveTimer = setInterval(tickLive, 1000);
    const frameTimer = setInterval(tickFrame, Math.round(1000 / target));
    return () => {
      clearInterval(liveTimer);
      clearInterval(frameTimer);
    };
    // overlay and the saved FPS are read when this effect restarts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id, overlay, camera?.ai_fps]);

  async function uploadVideo(file: File) {
    const body = new FormData();
    body.append("file", file);
    setSettingsError("");
    setUpload(`Uploading ${file.name}…`);
    try {
      const updated = await api<Camera>(`/api/cameras/${params.id}/video`, { method: "POST", body });
      setCamera(updated);
      setUpload(file.name);
      setMessage("Video saved. The worker will loop it as this camera. Zones stay where they were drawn; check them in Draw zones against the new view.");
    } catch (err) {
      setUpload("");
      setSettingsError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  // report shows the error where the change was made: in the settings drawer, or on the page for the header switch.
  async function save(partial: Partial<Camera>, report = setSettingsError) {
    report("");
    try {
      const updated = await api<Camera>(`/api/cameras/${params.id}`, { method: "PATCH", body: JSON.stringify(partial) });
      setCamera(updated);
      return updated;
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not save camera settings");
      return null;
    }
  }

  async function setEnabled(enabled: boolean) {
    setToggling(true);
    const updated = await save({ enabled }, setError);
    setToggling(false);
    if (updated) toast(enabled ? "Camera enabled · processing frames again" : "Camera disabled · no frames processed, no alerts raised");
  }

  // The slider saves once it settles, not on every step.
  function changeFps(value: number) {
    setFpsDraft(value);
    clearTimeout(fpsTimer.current);
    fpsTimer.current = setTimeout(async () => {
      if (!camera || value === camera.ai_fps) return;
      const updated = await save({ ai_fps: value });
      if (!updated) {
        setFpsDraft(camera.ai_fps);
        return;
      }
      setMessage(`AI FPS saved at ${value}. The worker picks it up on the next frame.`);
    }, 600);
  }
  useEffect(() => () => clearTimeout(fpsTimer.current), []);

  function simulate() {
    api(`/api/cameras/${params.id}/simulate`, { method: "POST" })
      .then(() => toast("Simulation queued · people will stand inside the zones for a few seconds"))
      .catch((err) => setError(err.message));
  }

  function closeSettings() {
    setSettingsOpen(false);
    setSettingsError("");
    setMessage("");
  }

  // Status from the live poll, every second: the camera record is read on load and after a change, so turned on
  // it still said Offline while frames were being processed.
  const isLive = LIVE.has(live?.status || camera?.status || "");
  const pausedZones = (live?.zones || []).filter((zone) => PAUSED_STATES.has(zone.state));
  const tracks = live?.tracks || [];
  const violations = tracks.filter((track) => verdict(track).chip === "Violation").length;
  // A fixed order, by id, so rows do not swap places every second as verdicts change. Vehicles go last.
  const ordered = [...tracks].sort((a, b) => Number(a.class_name !== "person") - Number(b.class_name !== "person") || Number(a.track_id) - Number(b.track_id));
  const clock = now ? formatTime(now) : "";
  // Label, value, hover hint. Measured and target FPS share one entry so the row stays on one line on a laptop screen.
  const stats = [
    ["AI FPS", `${live?.ai_fps ?? 0} / ${camera?.ai_fps ?? "—"}`, "Measured / target frames per second"],
    ["Inference", `${Math.round(live?.inference_ms || 0)} ms`, "Time the detector takes per frame"],
    ["Frames", String(live?.frames_processed ?? 0), "Frames processed"],
    ["Dropped", String(live?.dropped_frames ?? 0), "Frames skipped to keep up"],
  ];

  return (
    <Shell
      title={camera?.name || "Camera"}
      back={{ href: "/cameras", label: "Cameras" }}
      dense
      subtitle={
        camera ? (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {/* An admin turns the camera on and off right on its status, where the result shows; others see the status alone.
                Off is orange: a safety camera that watches nothing should catch the eye. */}
            {admin ? (
              <span className={`inline-flex items-center gap-2 rounded-full py-px pl-px pr-3 text-xs font-semibold ${!camera.enabled ? "bg-warn-50 text-warn-700" : isLive ? "bg-success-50 text-success-700" : "bg-well text-graphite-500"}`}>
                <Switch checked={camera.enabled} onChange={setEnabled} label={camera.enabled ? "Disable camera" : "Enable camera"} size="sm" disabled={toggling} />
                {camera.enabled ? (isLive ? "Camera on · Live" : "Camera on · Offline") : "Camera off"}
              </span>
            ) : (
              <span className={`inline-flex items-center gap-[7px] rounded-full px-2.5 py-1 text-xs font-semibold ${isLive ? "bg-success-50 text-success-700" : "bg-well text-graphite-500"}`}>
                <span className="h-[7px] w-[7px] rounded-full bg-current" />
                {camera.enabled ? (isLive ? "Live" : "Offline") : "Disabled"}
              </span>
            )}
            {/* Each fact stays whole when the line wraps on a phone. */}
            <span className="flex flex-wrap gap-x-1.5 font-mono text-[12.5px] text-graphite-500">
              {[camera.code, camera.area, `${ruleCount} ${ruleCount === 1 ? "rule" : "rules"}`].map((fact, index) => (
                <span key={index} className="whitespace-nowrap">{index ? "· " : ""}{fact}</span>
              ))}
            </span>
          </span>
        ) : null
      }
      actions={
        <>
          <OutlineButton onClick={() => router.push(`/cameras/${params.id}/zones`)}>Draw zones</OutlineButton>
          {canReview ? (
            <PrimaryButton onClick={simulate}>
              <span className="sm:hidden">Simulate</span>
              <span className="hidden sm:inline">Simulate an incident</span>
            </PrimaryButton>
          ) : null}
          {admin && camera ? (
            <GhostButton onClick={() => setSettingsOpen(true)} aria-label="Camera settings" className="flex items-center justify-center gap-2 px-3.5 py-[10px]">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px] shrink-0" aria-hidden="true">
                <path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h9M17 18h3" />
                <circle cx="15" cy="6" r="2" />
                <circle cx="9" cy="12" r="2" />
                <circle cx="15" cy="18" r="2" />
              </svg>
              <span className="hidden sm:inline">Settings</span>
            </GhostButton>
          ) : null}
        </>
      }
    >
      {error ? <ErrorText>{error}</ErrorText> : null}

      {/* Wide screen: the view on the left, sized to fit the screen height; the side column takes exactly the view's height and scrolls inside.
          Stacked: the view, then people and vehicles, zones and recent alerts. */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="panel flex min-w-0 flex-col gap-2.5 p-3 xl:self-start">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-1">
            {/* On a phone the figures take a line of their own, two to a row, and the controls sit under them on the right. */}
            <dl className="grid flex-1 basis-full grid-cols-2 items-baseline gap-x-4 gap-y-1 sm:flex sm:basis-0 sm:flex-wrap">
              {stats.map(([label, value, hint]) => (
                <div key={label} title={hint} className="flex items-baseline gap-1.5 whitespace-nowrap">
                  <dt className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-graphite-400">{label}</dt>
                  <dd className="font-mono text-[13px] font-medium text-graphite-800">{value}</dd>
                </div>
              ))}
            </dl>
            <span className="ml-auto flex items-center gap-2.5 whitespace-nowrap text-[13px] font-medium text-graphite-600">
              AI overlay
              <Switch checked={overlay} onChange={setOverlay} label="Show AI overlay" size="sm" tone="brand" />
            </span>
            {canFullscreen ? (
              <button type="button" onClick={() => stage.current?.requestFullscreen().catch(() => undefined)} aria-label="Full screen" title="Full screen" className="grid h-8 w-8 place-items-center border border-line bg-surface p-0 text-graphite-600 hover:bg-muted">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                  <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
                </svg>
              </button>
            ) : null}
          </div>
          {/* 284px is everything else on the screen above and below the view (top bar, header, this toolbar, padding), so the whole panel fits without scrolling. */}
          <div ref={stage} className="relative aspect-video w-full overflow-hidden rounded-lg bg-ink md:max-h-[calc(100dvh-284px)] md:min-h-[240px]">
            {frame ? (
              <img src={frame} alt="Latest camera frame" className={`absolute inset-0 h-full w-full object-contain transition-[filter] duration-300 ${camera?.enabled === false ? "brightness-[.72] grayscale-[.6]" : ""}`} />
            ) : (
              <div className="absolute inset-0 grid place-items-center bg-stripes font-mono text-xs text-fog-500">waiting for the first frame · {camera?.code}</div>
            )}
            {isLive && overlay && frame ? (
              <span className="pointer-events-none absolute inset-x-0 hidden h-0.5 bg-gradient-to-r from-transparent via-brand-400/90 to-transparent shadow-[0_0_12px_rgba(72,198,253,.55)] motion-safe:block motion-safe:animate-scan" aria-hidden="true" />
            ) : null}
            {pausedZones.length ? (
              <div className="absolute inset-x-3 top-3 rounded-lg bg-danger-600/95 px-3 py-2 text-[13px] text-white shadow-[0_6px_20px_rgba(10,21,37,.3)]">
                {pausedZones.map((zone) => zone.name).join(", ")} {pausedZones.length === 1 ? "is" : "are"} paused because the camera no longer shows {pausedZones.length === 1 ? "it" : "them"}. Rules there resume when the view matches again, or <Link href={`/cameras/${params.id}/zones`} className="font-semibold underline">redraw</Link> for the new view.
              </div>
            ) : null}
            <span className="absolute bottom-3 left-3 flex items-center gap-2 rounded bg-ink/80 px-2.5 py-[5px] font-mono text-[11px] text-fog-100">
              {isLive ? <RecDot /> : null}
              <span>{camera?.code}</span>
              <span className="h-1 w-1 rounded-full bg-brand-400" aria-hidden="true" />
              <span>{clock}</span>
            </span>
            {camera?.enabled === false ? (
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <span className="rounded-lg border border-white/15 bg-ink/85 px-4 py-2.5 text-[13px] font-medium text-white">Camera disabled · showing last frame</span>
              </div>
            ) : null}
          </div>
        </section>

        <div className="relative min-w-0 xl:min-h-[420px]">
          <div className="flex flex-col gap-4 xl:absolute xl:inset-0 xl:overflow-y-auto">
            <section className="panel-dark flex shrink-0 flex-col gap-3 p-4 xl:min-h-[200px] xl:flex-1 xl:shrink">
              <div className="relative flex items-baseline gap-2.5">
                <h2 className="flex-1 text-[15px] font-semibold text-fog-50">People and vehicles</h2>
                <span className="font-display text-2xl font-bold leading-none text-white">{tracks.length}</span>
              </div>
              {/* Stacked, a fixed cap that scrolls; in the side column it takes whatever height is left, so people coming and going never move the panels below. */}
              <div className="relative -mr-2 flex max-h-[300px] flex-col gap-2 overflow-y-auto pr-2 [scrollbar-gutter:stable] xl:max-h-none xl:min-h-0 xl:flex-1">
                {tracks.length === 0 ? <p className="text-[13.5px] text-fog-300">No person detected on the latest frame.</p> : null}
                {ordered.map((track) => {
                  const view = verdict(track);
                  const checks = track.checks || [];
                  return (
                    <div key={track.track_id + track.class_name} className="shrink-0 rounded-lg border border-ink-edge bg-ink-raised px-3 py-2.5">
                      <div className="flex items-center gap-2.5">
                        <span className={`grid h-6 min-w-[30px] shrink-0 place-items-center rounded border-2 px-1 font-mono text-[11px] text-fog-100 ${view?.box || "border-fog-500"}`}>{track.track_id}</span>
                        <span className="truncate text-sm font-semibold text-fog-50">{trackName(track)}</span>
                        <span className="font-mono text-[11px] text-fog-500">{Math.round((track.confidence || 0) * 100)}%</span>
                        {view ? <span className={`ml-auto whitespace-nowrap rounded-full px-2 py-[2px] text-[11px] font-semibold ${view.style}`}>{view.chip}</span> : null}
                      </div>
                      {checks.length ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {checks.map((check) => (
                            <span key={check.text} title={check.text} className={`whitespace-nowrap rounded px-1.5 py-[2px] text-[11.5px] font-semibold ${CHECK_CHIPS[check.state].style}`}>
                              {CHECK_CHIPS[check.state].mark} {check.item && ITEM_NAMES[check.item] ? ITEM_NAMES[check.item] : check.text}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-1.5 text-[12.5px] text-fog-300">Not in a zone with a rule</div>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="relative font-mono text-[11px] leading-relaxed text-fog-500">
                {camera?.enabled === false ? "Camera disabled — detections are from the last frame received." : `Latest frame · ${clock} · ${violations} ${violations === 1 ? "violation" : "violations"}`}
              </p>
            </section>

            {live?.zones?.length ? (
              <section className="panel shrink-0 px-4 py-3.5">
                <h2 className="text-[15px] font-semibold">Zones</h2>
                <ul className="mt-2.5 space-y-2 text-[13.5px]">
                  {live.zones.map((zone) => {
                    const state = ZONE_STATES[zone.state] || ZONE_STATES.UNVERIFIED;
                    return (
                      <li key={zone.id} className="flex flex-wrap items-center justify-between gap-2">
                        <span>{zone.name}</span>
                        <Badge value={state.label(zone)} tone={state.tone} />
                      </li>
                    );
                  })}
                </ul>
              </section>
            ) : null}

            <section className="panel shrink-0 overflow-hidden">
              <div className="flex items-center px-4 pb-2.5 pt-3.5">
                <h2 className="flex-1 text-[15px] font-semibold">Recent alerts</h2>
                <Link href={`/incidents?camera_id=${params.id}`} className="link text-[13px]">All →</Link>
              </div>
              {recent.length === 0 ? <p className="border-t border-line-soft px-4 pb-4 pt-3 text-[13px] text-graphite-500">No alerts from this camera yet.</p> : null}
              {/* Two lines a row, so it fits the side column: what and how bad, then when, where and the review status. */}
              {recent.map((item) => (
                <button key={item.id} onClick={() => openIncident(item.id)} className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-none border-t border-line-soft bg-transparent px-4 py-2.5 text-left font-normal text-graphite-800 hover:bg-subtle">
                  <span className="truncate text-[13.5px] font-medium">{eventLabel(item.event_type)}</span>
                  <span className="justify-self-end"><SeverityTag severity={item.severity} /></span>
                  <span className="truncate text-[12.5px] text-graphite-500">
                    <span className="font-mono text-brand-700">{formatTime(item.started_at)}</span> · {item.zone_name || "—"}
                  </span>
                  <span className="justify-self-end"><StatusPill status={item.status} /></span>
                </button>
              ))}
            </section>
          </div>
        </div>
      </div>

      {settingsOpen && admin && camera ? (
        <Drawer title="Camera settings" onClose={closeSettings}>
          {settingsError ? <ErrorText>{settingsError}</ErrorText> : null}
          {message ? <Notice>{message}</Notice> : null}
          <label className="flex flex-col gap-2">
            <span className="flex items-baseline">
              <span className="flex-1 text-[13px] font-semibold">AI FPS</span>
              <span className="font-mono text-[13px] text-brand-700">{fpsDraft ?? camera.ai_fps} / 30</span>
            </span>
            <input type="range" min={1} max={30} value={fpsDraft ?? camera.ai_fps} onChange={(e) => changeFps(Number(e.target.value))} />
            <span className="text-xs leading-normal text-graphite-400">Measured FPS is how fast this machine is actually running: {live?.ai_fps ?? 0} FPS now.</span>
          </label>
          {/* Enter saves as leaving the field does; Escape closes the drawer and drops the edit. */}
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">RTSP or file key</span>
            <input key={camera.stream_url || "none"} className="font-mono text-[12.5px]" defaultValue={camera.stream_url || ""} onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} onBlur={(e) => { if (e.target.value !== (camera.stream_url || "")) save({ stream_url: e.target.value }); }} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Assigned worker</span>
            <input defaultValue={camera.assigned_worker || ""} placeholder="Blank = any worker" onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} onBlur={(e) => { if (e.target.value !== (camera.assigned_worker || "")) save({ assigned_worker: e.target.value || null } as Partial<Camera>); }} />
          </label>
          <Checkbox
            checked={Boolean(camera.multi_view)}
            onChange={(next) => save({ multi_view: next })}
            label="Camera has several views"
            hint="For PTZ presets. Zones lock to one view; only the matching view is checked. Leave off for a fixed camera."
          />
          <label
            className="flex cursor-pointer flex-col items-center gap-1 rounded-[10px] border-[1.5px] border-dashed border-line-strong bg-subtle p-[18px] text-center transition-colors hover:border-brand-500 hover:bg-brand-50"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files?.[0];
              if (file) uploadVideo(file);
            }}
          >
            <input type="file" accept="video/mp4,.mp4" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) uploadVideo(file); }} />
            <span className="text-[13.5px] font-semibold text-brand-600">Upload MP4</span>
            <span className="text-xs text-graphite-400">{upload || "Drop a file here or click to browse"}</span>
          </label>
        </Drawer>
      ) : null}
    </Shell>
  );
}
