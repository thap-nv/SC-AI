"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/providers";
import Shell from "@/components/shell";
import { Badge, ErrorText, Notice, OutlineButton, PrimaryButton, RecDot, SeverityTag, StatusPill, Switch } from "@/components/ui";
import { api, Camera, getUser, imageUrl, Incident, Rule } from "@/lib/api";
import { useIncidentEvents } from "@/lib/live";
import { BEAN_LABELS, COFFEE_STAGE_LABELS, eventLabel, formatTime } from "@/lib/labels";

type Check = { text: string; state: "violation" | "ok" | "unknown" };

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

type CoffeeLine = {
  zone_id: string;
  name: string;
  stage: string;
  total: number;
  window_total: number;
  defects: number;
  defect_rate: number;
  by_class: Record<string, number>;
  in_frame: number;
};

type Track = { track_id: string; class_name: string; confidence: number; hairnet?: string; uniform?: string; checks?: Check[] };

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
  coffee?: CoffeeLine[];
};

// How a tracked person reads in the "People in view" card.
function verdict(track: Track) {
  const checks = track.checks || [];
  if (checks.some((check) => check.state === "violation")) return { chip: "Violation", box: "border-brand-500", style: "bg-brand-500/20 text-brand-200" };
  if (checks.length && checks.every((check) => check.state === "ok")) return { chip: "Compliant", box: "border-success-600", style: "bg-success-600/20 text-success-200" };
  return { chip: "Not checked", box: "border-fog-500", style: "bg-ink-edge text-fog-300" };
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
  const [message, setMessage] = useState("");
  const [role, setRole] = useState("");
  const [fpsDraft, setFpsDraft] = useState<number | null>(null);
  const [upload, setUpload] = useState("");
  const fpsTimer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => setRole(getUser()?.role || ""), []);
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
    setError("");
    setUpload(`Uploading ${file.name}…`);
    try {
      const updated = await api<Camera>(`/api/cameras/${params.id}/video`, { method: "POST", body });
      setCamera(updated);
      setUpload(file.name);
      setMessage("Video saved. The worker will loop it as this camera.");
    } catch (err) {
      setUpload("");
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function save(partial: Partial<Camera>) {
    setError("");
    try {
      const updated = await api<Camera>(`/api/cameras/${params.id}`, { method: "PATCH", body: JSON.stringify(partial) });
      setCamera(updated);
      return updated;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save camera settings");
      return null;
    }
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
      .then(() => toast("Simulation queued · a person will stand inside the zones for a few seconds"))
      .catch((err) => setError(err.message));
  }

  const isLive = camera ? LIVE.has(camera.status) : false;
  const pausedZones = (live?.zones || []).filter((zone) => PAUSED_STATES.has(zone.state));
  const tracks = live?.tracks || [];
  const people = tracks.filter((track) => track.class_name === "person");
  const violations = people.filter((track) => verdict(track).chip === "Violation").length;
  const clock = now ? formatTime(now) : "";
  const stats = [
    ["Measured", `${live?.ai_fps ?? 0} FPS`],
    ["Target", `${camera?.ai_fps ?? "—"} FPS`],
    ["Inference", `${Math.round(live?.inference_ms || 0)} ms`],
    ["Frames", String(live?.frames_processed ?? 0)],
    ["Dropped", String(live?.dropped_frames ?? 0)],
  ];

  return (
    <Shell
      title={camera?.name || "Camera"}
      back={{ href: "/cameras", label: "Cameras" }}
      actions={
        <>
          <OutlineButton onClick={() => router.push(`/cameras/${params.id}/zones`)}>Draw zones</OutlineButton>
          {canReview ? <PrimaryButton onClick={simulate}>Simulate an incident</PrimaryButton> : null}
        </>
      }
    >
      <div className="-mt-1.5 flex flex-wrap items-center gap-3">
        {camera ? (
          <span className={`inline-flex items-center gap-[7px] rounded-full px-2.5 py-1 text-xs font-semibold ${isLive ? "bg-success-50 text-success-700" : "bg-well text-graphite-500"}`}>
            <span className="h-[7px] w-[7px] rounded-full bg-current" />
            {camera.enabled ? (isLive ? "Live" : "Offline") : "Disabled"}
          </span>
        ) : null}
        <span className="font-mono text-[12.5px] text-graphite-500">{camera?.code} · {camera?.area} · {camera?.ai_fps} FPS · {ruleCount} {ruleCount === 1 ? "rule" : "rules"}</span>
      </div>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {message ? <Notice>{message}</Notice> : null}

      <div className="flex flex-wrap items-start gap-5">
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <section className="panel flex flex-col gap-3.5 p-4">
            <div className="flex flex-wrap items-center gap-3 px-1">
              <h2 className="flex-1 text-base font-semibold">Camera view</h2>
              <span className="flex items-center gap-2.5 text-[13px] font-medium text-graphite-600">
                Show AI overlay
                <Switch checked={overlay} onChange={setOverlay} label="Show AI overlay" size="sm" tone="brand" />
              </span>
            </div>
            {pausedZones.length ? (
              <div className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">
                {pausedZones.map((zone) => zone.name).join(", ")} {pausedZones.length === 1 ? "is" : "are"} paused because the camera no longer shows {pausedZones.length === 1 ? "it" : "them"}. Rules there resume when the view matches again, or <Link href={`/cameras/${params.id}/zones`} className="underline">redraw</Link> for the new view.
              </div>
            ) : null}
            <div className="relative aspect-video overflow-hidden rounded-lg bg-ink">
              {frame ? (
                <img src={frame} alt="Latest camera frame" className={`absolute inset-0 h-full w-full object-contain transition-[filter] duration-300 ${camera?.enabled === false ? "brightness-[.72] grayscale-[.6]" : ""}`} />
              ) : (
                <div className="absolute inset-0 grid place-items-center bg-stripes font-mono text-xs text-fog-500">waiting for the first frame · {camera?.code}</div>
              )}
              {isLive && overlay && frame ? (
                <span className="pointer-events-none absolute inset-x-0 hidden h-0.5 bg-gradient-to-r from-transparent via-brand-400/90 to-transparent shadow-[0_0_12px_rgba(238,0,51,.55)] motion-safe:block motion-safe:animate-scan" aria-hidden="true" />
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
            <dl className="grid grid-cols-[repeat(auto-fit,minmax(104px,1fr))] gap-px overflow-hidden rounded-lg border border-line-muted bg-line-muted">
              {stats.map(([label, value]) => (
                <div key={label} className="flex flex-col gap-0.5 bg-subtle px-3 py-2.5">
                  <dt className="text-[11px] uppercase tracking-[0.06em] text-graphite-400">{label}</dt>
                  <dd className="font-mono text-sm font-medium text-graphite-800">{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="panel overflow-hidden">
            <div className="flex items-center px-5 pb-3 pt-4">
              <h2 className="flex-1 text-[15px] font-semibold">Recent alerts on this camera</h2>
              <Link href={`/incidents?camera_id=${params.id}`} className="link text-[13px]">All →</Link>
            </div>
            {recent.length === 0 ? <p className="border-t border-line-soft px-5 pb-[18px] pt-3.5 text-[13px] text-graphite-500">No alerts from this camera yet.</p> : null}
            {recent.map((item) => (
              <button key={item.id} onClick={() => openIncident(item.id)} className="flex w-full flex-wrap items-center gap-x-3.5 gap-y-1.5 rounded-none border-t border-line-soft bg-transparent px-5 py-[11px] text-left text-graphite-800 hover:bg-subtle">
                <span className="w-[72px] font-mono text-[12.5px] text-brand-700">{formatTime(item.started_at)}</span>
                <span className="min-w-0 flex-[1_1_180px] text-[13.5px] font-medium">
                  {eventLabel(item.event_type)} <span className="font-normal text-graphite-400">· {item.zone_name || "—"}</span>
                </span>
                <span className="flex items-center gap-2.5">
                  <SeverityTag severity={item.severity} />
                  <StatusPill status={item.status} />
                </span>
              </button>
            ))}
          </section>
        </div>

        <div className="flex min-w-0 max-w-full flex-[1_1_300px] flex-col gap-5">
          <section className="panel-dark flex flex-col gap-3.5 p-5">
            <div className="relative flex items-baseline gap-2.5">
              <h2 className="flex-1 text-base font-semibold text-fog-50">People in view</h2>
              <span className="font-display text-2xl font-bold text-white">{people.length}</span>
            </div>
            {tracks.length === 0 ? <p className="text-[13.5px] text-fog-300">No person detected on the latest frame.</p> : null}
            {tracks.map((track) => {
              const person = track.class_name === "person";
              const view = person ? verdict(track) : null;
              const status = person ? (track.checks?.length ? track.checks.map((check) => check.text).join(" · ") : "Not in a zone with a rule") : "Vehicle";
              return (
                <div key={track.track_id + track.class_name} className="relative flex items-center gap-3 rounded-lg border border-ink-edge bg-ink-raised p-3">
                  <span className={`grid h-[34px] w-[34px] shrink-0 place-items-center rounded-md border-2 font-mono text-[11px] text-fog-100 ${view?.box || "border-fog-500"}`}>{track.track_id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-fog-50">{person ? `Person ${track.track_id}` : `Forklift ${track.track_id}`}</span>
                    <span className="block text-[12.5px] text-fog-300">{status} · {Math.round((track.confidence || 0) * 100)}% confidence</span>
                  </span>
                  {view ? <span className={`whitespace-nowrap rounded-full px-2.5 py-[3px] text-[11.5px] font-semibold ${view.style}`}>{view.chip}</span> : null}
                </div>
              );
            })}
            <p className="relative font-mono text-[11px] leading-relaxed text-fog-500">
              {camera?.enabled === false ? "Camera disabled — detections are from the last frame received." : `Latest frame · ${clock} · ${violations} ${violations === 1 ? "violation" : "violations"}`}
            </p>
          </section>

          {live?.coffee?.length ? (
            <section className="panel p-5">
              <h2 className="text-base font-semibold">Coffee on the belt</h2>
              <div className="mt-3 space-y-3">
                {live.coffee.map((line) => (
                  <div key={line.zone_id} className="rounded-lg bg-subtle px-3 py-2.5 text-sm">
                    <div className="font-semibold">{line.name}</div>
                    <div className="text-graphite-500">{COFFEE_STAGE_LABELS[line.stage] || line.stage}</div>
                    <div className="mt-1 font-mono text-[12.5px]">{line.total} counted · {line.in_frame} in frame{line.stage === "count" ? "" : ` · ${Math.round((line.defect_rate || 0) * 100)}% defects in the last ${line.window_total}`}</div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {Object.entries(line.by_class || {}).map(([name, count]) => (
                        <Badge key={name} value={`${BEAN_LABELS[name] || name} ${count}`} tone={name === "good" || name === "bean" ? "green" : "red"} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {live?.zones?.length ? (
            <section className="panel p-5">
              <h2 className="text-base font-semibold">Zones</h2>
              <ul className="mt-3 space-y-2 text-sm">
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

          {admin && camera ? (
            <section className="panel flex flex-col gap-4 p-5">
              <h2 className="text-base font-semibold">Camera settings</h2>
              <div className="flex items-center gap-3 rounded-[10px] bg-muted px-3.5 py-3">
                <div className="flex-1">
                  <div className="text-sm font-semibold">Enable camera</div>
                  <div className="text-xs text-graphite-500">{camera.enabled ? "Processing frames now" : "Not processing frames"}</div>
                </div>
                <Switch checked={camera.enabled} onChange={(enabled) => save({ enabled })} label="Enable camera" />
              </div>
              <label className="flex flex-col gap-2">
                <span className="flex items-baseline">
                  <span className="flex-1 text-[13px] font-semibold">AI FPS</span>
                  <span className="font-mono text-[13px] text-brand-700">{fpsDraft ?? camera.ai_fps} / 30</span>
                </span>
                <input type="range" min={1} max={30} value={fpsDraft ?? camera.ai_fps} onChange={(e) => changeFps(Number(e.target.value))} />
                <span className="text-xs leading-normal text-graphite-400">Measured FPS is how fast this machine is actually running.</span>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-[13px] font-semibold">RTSP or file key</span>
                <input key={camera.stream_url || "none"} className="font-mono text-[12.5px]" defaultValue={camera.stream_url || ""} onBlur={(e) => { if (e.target.value !== (camera.stream_url || "")) save({ stream_url: e.target.value }); }} />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-[13px] font-semibold">Assigned worker</span>
                <input defaultValue={camera.assigned_worker || ""} placeholder="Blank = any worker" onBlur={(e) => { if (e.target.value !== (camera.assigned_worker || "")) save({ assigned_worker: e.target.value || null } as Partial<Camera>); }} />
              </label>
              <button
                type="button"
                role="checkbox"
                aria-checked={Boolean(camera.multi_view)}
                onClick={() => save({ multi_view: !camera.multi_view })}
                className="flex items-start gap-3 rounded-none bg-transparent p-0 text-left font-normal text-graphite-800"
              >
                <span className={`mt-px grid h-[18px] w-[18px] shrink-0 place-items-center rounded border-[1.5px] text-xs font-bold text-surface ${camera.multi_view ? "border-brand-500 bg-brand-500" : "border-line-strong bg-surface"}`}>{camera.multi_view ? "✓" : ""}</span>
                <span className="flex flex-col gap-[3px]">
                  <span className="text-[13.5px] font-semibold">Camera has several views</span>
                  <span className="text-xs leading-normal text-graphite-400">For PTZ presets. Zones lock to one view; only the matching view is checked. Leave off for a fixed camera.</span>
                </span>
              </button>
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
            </section>
          ) : null}
        </div>
      </div>
    </Shell>
  );
}
