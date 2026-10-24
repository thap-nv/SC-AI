"use client";

import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/providers";
import Shell from "@/components/shell";
import { ErrorText, GhostButton, Segmented, SeverityTag, StatusPill } from "@/components/ui";
import { api, Camera, Incident, Zone } from "@/lib/api";
import { useIncidentEvents } from "@/lib/live";
import { eventLabel, EVENT_LABELS, formatDay, formatTime } from "@/lib/labels";

type Filters = { on_date: string; camera_id: string; zone_id: string; event_type: string; severity: string; status: string };

const EMPTY: Filters = { on_date: "", camera_id: "", zone_id: "", event_type: "", severity: "", status: "" };
const PAGE = 100;

const SEVERITY_TABS = [
  { value: "", label: "All" },
  { value: "CRITICAL", label: "Critical" },
  { value: "HIGH", label: "High" },
  { value: "MEDIUM", label: "Medium" },
  { value: "LOW", label: "Low" },
];

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "NEW", label: "New" },
  { value: "CONFIRMED", label: "Confirmed" },
  { value: "FALSE_POSITIVE", label: "False positive" },
  { value: "RESOLVED", label: "Resolved" },
];

function confidenceColor(value: number) {
  if (value >= 0.8) return "bg-success-600";
  if (value >= 0.6) return "bg-warn-500";
  return "bg-danger-500";
}

// A critical alert nobody has looked at yet gets a red row.
function urgent(item: Incident) {
  return item.status === "NEW" && item.severity === "CRITICAL";
}

export default function IncidentsPage() {
  const { openIncident } = useApp();
  const [items, setItems] = useState<Incident[]>([]);
  const [total, setTotal] = useState(0);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [error, setError] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const shown = useRef(PAGE);

  function load(next = filters, limit = shown.current) {
    const params = new URLSearchParams();
    Object.entries(next).forEach(([key, value]) => value && params.set(key, value));
    params.set("limit", String(Math.min(200, limit)));
    api<{ items: Incident[]; total: number }>(`/api/incidents?${params.toString()}`)
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    api<Camera[]>("/api/cameras").then(setCameras).catch(() => undefined);
    api<Zone[]>("/api/zones").then(setZones).catch(() => undefined);
    // Links such as "View all →" open this page pre-filtered.
    const query = new URLSearchParams(window.location.search);
    const initial = { ...EMPTY };
    (Object.keys(EMPTY) as (keyof Filters)[]).forEach((key) => {
      initial[key] = query.get(key) || "";
    });
    setFilters(initial);
    load(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useIncidentEvents(() => load(), 800);

  function update(key: keyof Filters, value: string) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    shown.current = PAGE;
    load(next, PAGE);
  }

  // On a phone only the status tabs stay out; severity, camera, zone, violation and date fold behind "Filters".
  const folded = [filters.severity, filters.camera_id, filters.zone_id, filters.event_type, filters.on_date].filter(Boolean).length;

  return (
    <Shell title="Incidents">
      <div className="flex flex-wrap items-center gap-3">
        <div className="hidden md:block">
          <Segmented label="Severity" options={SEVERITY_TABS} value={filters.severity} onChange={(value) => update("severity", value)} />
        </div>
        <div className="w-full md:w-auto">
          <Segmented label="Status" options={STATUS_TABS} value={filters.status} onChange={(value) => update("status", value)} />
        </div>
        <button type="button" onClick={() => setShowFilters((open) => !open)} aria-expanded={showFilters} aria-controls="incident-filters" className="border border-line-strong bg-surface text-[13px] font-semibold text-graphite-800 md:hidden">
          Filters{folded ? ` · ${folded}` : ""} <span aria-hidden="true">{showFilters ? "▴" : "▾"}</span>
        </button>
        <div className="flex-1" />
        <span className="text-[13px] text-graphite-500"><strong className="text-graphite-800">{total}</strong> incidents</span>
      </div>
      <div id="incident-filters" className={`-mt-2 gap-2.5 ${showFilters ? "grid grid-cols-2" : "hidden"} md:flex md:flex-wrap`}>
        <select aria-label="Severity" className="min-w-0 py-2 text-[13px] md:hidden" value={filters.severity} onChange={(e) => update("severity", e.target.value)}>
          {SEVERITY_TABS.map((tab) => <option key={tab.value} value={tab.value}>{tab.value ? tab.label : "All severities"}</option>)}
        </select>
        <select aria-label="Camera" className="min-w-0 py-2 text-[13px] md:w-auto" value={filters.camera_id} onChange={(e) => update("camera_id", e.target.value)}>
          <option value="">All cameras</option>
          {cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}
        </select>
        <select aria-label="Zone" className="min-w-0 py-2 text-[13px] md:w-auto" value={filters.zone_id} onChange={(e) => update("zone_id", e.target.value)}>
          <option value="">All zones</option>
          {zones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
        </select>
        <select aria-label="Violation" className="min-w-0 py-2 text-[13px] md:w-auto" value={filters.event_type} onChange={(e) => update("event_type", e.target.value)}>
          <option value="">All violations</option>
          {Object.entries(EVENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <input aria-label="Date" type="date" className="min-w-0 py-2 text-[13px] md:w-auto" value={filters.on_date} onChange={(e) => update("on_date", e.target.value)} />
      </div>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {/* Phone: one card per incident, with what a reviewer scans for first; the table needs a wide screen. */}
      <div className="panel divide-y divide-line-soft overflow-hidden md:hidden">
        {items.length === 0 ? <p className="px-4 py-6 text-sm text-graphite-500">No incidents match these filters.</p> : null}
        {items.map((item) => (
          <button key={item.id} onClick={() => openIncident(item.id)} className={`flex w-full items-start gap-3 rounded-none px-4 py-3 text-left font-normal text-graphite-800 ${urgent(item) ? "bg-danger-50" : "bg-transparent hover:bg-subtle"}`}>
            <span className="flex w-[62px] shrink-0 flex-col pt-px">
              <span className="font-mono text-[12.5px] text-brand-700">{formatTime(item.started_at)}</span>
              <span className="text-[11px] text-graphite-400">{formatDay(item.started_at)}</span>
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="text-sm font-semibold">{eventLabel(item.event_type)}</span>
              <span className="truncate text-[12.5px] text-graphite-500">{item.camera_name}{item.zone_name ? ` · ${item.zone_name}` : ""}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-2">
                <SeverityTag severity={item.severity} />
                <StatusPill status={item.status} />
                {item.confidence === null ? null : <span className="font-mono text-[11.5px] text-graphite-500">AI {Math.round(item.confidence * 100)}%</span>}
              </span>
            </span>
            <span className="self-center text-base text-graphite-300" aria-hidden="true">›</span>
          </button>
        ))}
      </div>
      <div className="panel hidden overflow-auto md:block">
        <table className="min-w-[1000px]">
          <thead>
            <tr><th>Time</th><th>Camera</th><th>Zone</th><th>Violation</th><th>Severity</th><th>AI confidence</th><th>Status</th><th aria-label="Open" /></tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={8} className="py-7 text-sm text-graphite-500">No incidents match these filters.</td></tr>
            ) : null}
            {items.map((item) => (
              <tr key={item.id} onClick={() => openIncident(item.id)} className={`cursor-pointer ${urgent(item) ? "bg-danger-50" : ""}`}>
                <td>
                  <button className="flex flex-col items-start rounded-none bg-transparent p-0 text-left" onClick={(e) => { e.stopPropagation(); openIncident(item.id); }}>
                    <span className="font-mono text-[12.5px] text-brand-700">{formatTime(item.started_at)}</span>
                    <span className="text-[11px] font-normal text-graphite-300">{formatDay(item.started_at)}</span>
                  </button>
                </td>
                <td className="text-[13.5px]">{item.camera_name}</td>
                <td className="text-[13.5px] text-graphite-600">{item.zone_name || "—"}</td>
                <td className="text-[13.5px] font-medium">{eventLabel(item.event_type)}</td>
                <td><SeverityTag severity={item.severity} /></td>
                <td>
                  {item.confidence === null ? (
                    <span className="text-graphite-400">—</span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <span className="h-[5px] w-24 overflow-hidden rounded-[3px] bg-line-muted">
                        <span className={`block h-full ${confidenceColor(item.confidence)}`} style={{ width: `${Math.round(item.confidence * 100)}%` }} />
                      </span>
                      <span className="w-[34px] font-mono text-xs">{Math.round(item.confidence * 100)}%</span>
                    </span>
                  )}
                </td>
                <td><StatusPill status={item.status} /></td>
                <td className="text-base text-graphite-300" aria-hidden="true">›</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {items.length < total ? (
        <div className="flex items-center justify-center gap-3 text-[13px] text-graphite-500">
          Showing {items.length} of {total}
          {shown.current < 200 ? (
            <GhostButton onClick={() => { shown.current = 200; load(filters, 200); }}>Show more</GhostButton>
          ) : (
            <span>· narrow the filters to see older incidents</span>
          )}
        </div>
      ) : null}
    </Shell>
  );
}
