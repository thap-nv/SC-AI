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

  function apply(next: Filters) {
    setFilters(next);
    shown.current = PAGE;
    load(next, PAGE);
  }

  function update(key: keyof Filters, value: string) {
    const next = { ...filters, [key]: value };
    // A zone belongs to one camera; picking another camera drops a zone it does not have.
    if (key === "camera_id" && value && zones.find((zone) => zone.id === filters.zone_id)?.camera_id !== value) next.zone_id = "";
    apply(next);
  }

  // On a phone only the status tabs stay out; severity, camera, zone, violation and date fold behind "Filters".
  const folded = [filters.severity, filters.camera_id, filters.zone_id, filters.event_type, filters.on_date].filter(Boolean).length;
  const filtered = folded > 0 || Boolean(filters.status);
  const zoneChoices = filters.camera_id ? zones.filter((zone) => zone.camera_id === filters.camera_id) : zones;
  // Phone: a full-width cell of the folded grid. Wide screen: a control in the one filter row, as tall as the status tabs and,
  // where the browser supports it, only as wide as the value it shows, so "All cameras" takes less room than the longest camera name.
  const control = "min-w-0 py-2 text-[13px] md:h-10 md:w-auto md:max-w-[220px] md:py-0 md:[field-sizing:content]";
  const today = formatDay(new Date());
  const more = items.length >= total ? null : shown.current < 200 ? (
    <GhostButton onClick={() => { shown.current = 200; load(filters, 200); }} className="px-3 py-1.5 text-[13px]">Show more</GhostButton>
  ) : (
    <span>Narrow the filters to see older incidents</span>
  );

  return (
    <Shell title="Incidents" dense fill>
      {/* Every filter in one bar. On a phone it sticks under the top bar; from md the table scrolls in its own panel, so the bar never leaves the screen. */}
      <div className="sticky top-14 z-[4] -mx-4 -my-2 flex flex-wrap items-center gap-2.5 bg-paper/95 px-4 py-2 backdrop-blur md:static md:m-0 md:gap-2 md:bg-transparent md:p-0 md:backdrop-blur-none">
        <div className="w-full md:w-auto">
          <Segmented label="Status" options={STATUS_TABS} value={filters.status} onChange={(value) => update("status", value)} />
        </div>
        <button type="button" onClick={() => setShowFilters((open) => !open)} aria-expanded={showFilters} aria-controls="incident-filters" className="border border-line-strong bg-surface text-[13px] font-semibold text-graphite-800 md:hidden">
          Filters{folded ? ` · ${folded}` : ""} <span aria-hidden="true">{showFilters ? "▴" : "▾"}</span>
        </button>
        <div id="incident-filters" className={`order-last w-full gap-2.5 md:order-none md:contents ${showFilters ? "grid grid-cols-2" : "hidden"}`}>
          <select aria-label="Severity" className={control} value={filters.severity} onChange={(e) => update("severity", e.target.value)}>
            {SEVERITY_TABS.map((tab) => <option key={tab.value} value={tab.value}>{tab.value ? tab.label : "All severities"}</option>)}
          </select>
          <select aria-label="Camera" className={control} value={filters.camera_id} onChange={(e) => update("camera_id", e.target.value)}>
            <option value="">All cameras</option>
            {cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}
          </select>
          <select aria-label="Zone" className={control} value={filters.zone_id} onChange={(e) => update("zone_id", e.target.value)}>
            <option value="">All zones</option>
            {zoneChoices.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
          </select>
          <select aria-label="Violation" className={control} value={filters.event_type} onChange={(e) => update("event_type", e.target.value)}>
            <option value="">All violations</option>
            {Object.entries(EVENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
          <input aria-label="Date" type="date" className={control} value={filters.on_date} onChange={(e) => update("on_date", e.target.value)} />
        </div>
        {filtered ? <button type="button" onClick={() => apply(EMPTY)} className="link bg-transparent px-1.5 text-[13px]">Clear</button> : null}
        {/* Wide screen: the count sits in the bar under the table. */}
        <span className="ml-auto whitespace-nowrap text-[13px] text-graphite-500 md:hidden"><strong className="text-graphite-800">{total}</strong> incidents</span>
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
      {/* Wide screen: the panel takes the height left under the filters and scrolls inside, with the column names pinned. */}
      <div className="hidden min-h-[240px] flex-1 flex-col md:flex">
        <div className="panel flex min-h-0 flex-col overflow-hidden">
          <div className="min-h-0 overflow-auto">
            {/* One line a row. Below 2xl the cells pack tighter and today's rows drop the date, so a laptop screen still fits every column. */}
            <table className="min-w-[1000px] whitespace-nowrap [&_td]:px-3 [&_th]:px-3 2xl:[&_td]:px-4 2xl:[&_th]:px-4">
              <thead className="sticky-head">
                <tr><th>Time</th><th>Camera</th><th>Zone</th><th>Violation</th><th>Severity</th><th>AI confidence</th><th>Status</th><th aria-label="Open" /></tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr><td colSpan={8} className="py-7 text-sm text-graphite-500">No incidents match these filters.</td></tr>
                ) : null}
                {items.map((item) => (
                  <tr key={item.id} onClick={() => openIncident(item.id)} className={`cursor-pointer ${urgent(item) ? "bg-danger-50" : ""}`}>
                    <td className="py-2.5">
                      <button className="flex items-baseline gap-2 rounded-none bg-transparent p-0 text-left" onClick={(e) => { e.stopPropagation(); openIncident(item.id); }}>
                        <span className="font-mono text-[12.5px] text-brand-700">{formatTime(item.started_at)}</span>
                        {formatDay(item.started_at) === today ? null : <span className="text-[11.5px] font-normal text-graphite-400">{formatDay(item.started_at)}</span>}
                      </button>
                    </td>
                    <td className="py-2.5 text-[13.5px]">{item.camera_name}</td>
                    <td className="py-2.5 text-[13.5px] text-graphite-600">{item.zone_name || "—"}</td>
                    <td className="py-2.5 text-[13.5px] font-medium">{eventLabel(item.event_type)}</td>
                    <td className="py-2.5"><SeverityTag severity={item.severity} /></td>
                    <td className="py-2.5">
                      {item.confidence === null ? (
                        <span className="text-graphite-400">—</span>
                      ) : (
                        <span className="flex items-center gap-2">
                          <span className="h-[5px] w-14 overflow-hidden rounded-[3px] bg-line-muted 2xl:w-24">
                            <span className={`block h-full ${confidenceColor(item.confidence)}`} style={{ width: `${Math.round(item.confidence * 100)}%` }} />
                          </span>
                          <span className="w-[34px] font-mono text-xs">{Math.round(item.confidence * 100)}%</span>
                        </span>
                      )}
                    </td>
                    <td className="py-2.5"><StatusPill status={item.status} /></td>
                    <td className="py-2.5 text-base text-graphite-300" aria-hidden="true">›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex shrink-0 items-center gap-3 border-t border-line-soft bg-subtle px-4 py-2 text-[13px] text-graphite-500">
            <span>{items.length < total ? `Showing ${items.length} of ` : ""}<strong className="text-graphite-800">{total}</strong> incidents</span>
            <div className="flex-1" />
            {more}
          </div>
        </div>
      </div>
      {items.length < total ? (
        <div className="-mt-1.5 flex items-center justify-center gap-3 text-[13px] text-graphite-500 md:hidden">
          Showing {items.length} of {total}
          {more}
        </div>
      ) : null}
    </Shell>
  );
}
