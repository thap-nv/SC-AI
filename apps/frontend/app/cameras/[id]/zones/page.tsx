"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/shell";
import { Checkbox, ErrorText, GhostButton, PrimaryButton } from "@/components/ui";
import { api, getUser, imageUrl, Zone } from "@/lib/api";
import { ZONE_LABELS } from "@/lib/labels";

const TYPES = Object.keys(ZONE_LABELS);

export default function ZonesPage() {
  const params = useParams<{ id: string }>();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [points, setPoints] = useState<number[][]>([]);
  const [name, setName] = useState("PPE area");
  const [zoneType, setZoneType] = useState("PPE_ZONE");
  const [editing, setEditing] = useState<Zone | null>(null);
  // Whether the zone being saved follows camera moves (locked to the frozen frame) or stays where it is drawn.
  const [follow, setFollow] = useState(true);
  const [referenceId, setReferenceId] = useState<string | null>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [error, setError] = useState("");
  const [admin, setAdmin] = useState(false);
  useEffect(() => setAdmin(getUser()?.role === "ADMIN"), []);

  function loadZones() {
    api<Zone[]>(`/api/zones?camera_id=${params.id}`).then(setZones).catch((err) => setError(err.message));
  }

  useEffect(() => {
    loadZones();
    const show = (url: string) => {
      const img = new Image();
      img.onload = () => setImage(img);
      img.src = url;
    };
    const showLatest = () => imageUrl(`/api/cameras/${params.id}/snapshot?raw=true`).then(show).catch(() => setImage(null));
    if (getUser()?.role !== "ADMIN") {
      showLatest();
      return;
    }
    // Freeze the frame an admin draws on, so saved zones can follow the camera if it moves later.
    api<{ id: string }>(`/api/cameras/${params.id}/reference-frames`, { method: "POST" })
      .then(({ id }) => {
        setReferenceId(id);
        return imageUrl(`/api/cameras/${params.id}/reference-frames/${id}`).then(show);
      })
      .catch(() => {
        setReferenceId(null);
        showLatest();
      });
  }, [params.id]);

  // Redraw when the window resizes, since strokes and labels are sized from the canvas's displayed width.
  const [viewport, setViewport] = useState(0);
  useEffect(() => {
    const resize = () => setViewport(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = 960;
    const height = 540;
    // The canvas draws at 960 × 540 and is scaled to fit. k grows strokes, corners and labels by the same factor, so they
    // read at the same size on a phone as on a wide screen.
    const k = Math.max(1, width / (canvas.clientWidth || width));
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    const fontFamily = getComputedStyle(canvas).fontFamily;
    if (image) ctx.drawImage(image, 0, 0, width, height);
    else {
      ctx.fillStyle = "#0D1F35";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#8392A7";
      ctx.font = `${14 * k}px ${fontFamily}`;
      ctx.fillText("Waiting for a camera frame", 24 * k, 32 * k);
    }
    const draw = (poly: number[][], color: string, close: boolean, options: { dashed?: boolean; label?: string; labelText?: string } = {}) => {
      if (poly.length === 0) return;
      ctx.beginPath();
      poly.forEach(([x, y], index) => {
        const px = x * width;
        const py = y * height;
        if (index === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      if (close) ctx.closePath();
      ctx.setLineDash(options.dashed ? [8 * k, 6 * k] : []);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2 * k;
      ctx.stroke();
      ctx.setLineDash([]);
      if (close && !options.dashed) {
        ctx.fillStyle = color + "33";
        ctx.fill();
      }
      if (!options.dashed) {
        poly.forEach(([x, y]) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(x * width, y * height, 4 * k, 0, Math.PI * 2);
          ctx.fill();
        });
      }
      if (options.label) {
        const [x, y] = poly[0];
        ctx.font = `600 ${13 * k}px ${fontFamily}`;
        const textWidth = ctx.measureText(options.label).width;
        const top = Math.max(0, y * height - 24 * k);
        ctx.fillStyle = color;
        ctx.fillRect(x * width, top, textWidth + 10 * k, 20 * k);
        ctx.fillStyle = options.labelText || "#ffffff";
        ctx.fillText(options.label, x * width + 5 * k, top + 14 * k);
      }
    };
    // Saved zones wear Madison cyan (navy label, white would not read); the shape being drawn is indigo so it never reads as saved.
    zones.forEach((zone) => {
      if (zone.id === editing?.id) draw(zone.polygon, "#7A869A", true, { dashed: true, label: `${zone.name} (current)` });
      else draw(zone.polygon, "#48C6FD", true, { label: zone.name, labelText: "#0A1525" });
    });
    draw(points, "#4F5FE0", points.length > 2);
  }, [image, zones, points, editing, viewport]);

  function addPoint(event: React.MouseEvent<HTMLCanvasElement>) {
    if (!admin) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    setPoints((current) => [...current, [Number(x.toFixed(4)), Number(y.toFixed(4))]]);
  }

  function startRedraw(zone: Zone) {
    setError("");
    setEditing(zone);
    setName(zone.name);
    setZoneType(zone.zone_type);
    setFollow(Boolean(zone.reference_key));
    setPoints([]);
  }

  function stopRedraw() {
    setEditing(null);
    setName("PPE area");
    setZoneType("PPE_ZONE");
    setFollow(true);
    setPoints([]);
  }

  async function save() {
    setError("");
    try {
      // A new shape sent without a reference frame is saved unlinked.
      const reference = referenceId && follow ? { reference_id: referenceId } : {};
      if (editing) {
        await api(`/api/zones/${editing.id}`, { method: "PATCH", body: JSON.stringify({ name, polygon: points, ...reference }) });
        stopRedraw();
      } else {
        await api("/api/zones", { method: "POST", body: JSON.stringify({ camera_id: params.id, name, zone_type: zoneType, polygon: points, ...reference }) });
        setPoints([]);
      }
      loadZones();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the zone");
    }
  }

  // Lock a zone's current shape to the frame on screen, or pass null to unlink it so it stays where it is drawn.
  async function setView(zone: Zone, reference: string | null) {
    setError("");
    try {
      await api(`/api/zones/${zone.id}`, { method: "PATCH", body: JSON.stringify({ reference_id: reference }) });
      loadZones();
    } catch (err) {
      setError(err instanceof Error ? err.message : reference ? "Could not lock the zone to this view" : "Could not unlink the zone");
    }
  }

  // Zones locked to the same frame belong to one view; number the views in list order.
  const viewNumbers = new Map<string, number>();
  zones.forEach((zone) => {
    if (zone.reference_key && !viewNumbers.has(zone.reference_key)) viewNumbers.set(zone.reference_key, viewNumbers.size + 1);
  });

  return (
    <Shell title="Zone configuration" back={{ href: `/cameras/${params.id}`, label: "Camera" }}>
      <p className="-mt-2 text-sm text-graphite-500">Points are saved as fractions of the frame, from 0 to 1.</p>
      {error ? <ErrorText>{error}</ErrorText> : null}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <canvas ref={canvasRef} onClick={addPoint} className="w-full cursor-crosshair panel" />
        <div className="space-y-3">
          {admin ? (
            <div className="panel space-y-3 p-5">
              <h2 className="text-sm font-semibold">{editing ? `Redraw ${editing.name}` : "New zone"}</h2>
              <label className="block text-sm font-medium">Zone name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
              <label className="block text-sm font-medium">Zone type
                <select value={zoneType} onChange={(e) => setZoneType(e.target.value)} disabled={Boolean(editing)}>
                  {TYPES.map((type) => <option key={type} value={type}>{ZONE_LABELS[type]}</option>)}
                </select>
              </label>
              {zoneType === "PPE_ZONE" ? (
                <p className="text-xs text-graphite-500">Draw the floor where PPE is required. A person counts as inside where their feet are. Add the helmet, protective clothing and mask rules for this zone on the Rules page.</p>
              ) : null}
              {zoneType === "RESTRICTED_AREA" ? (
                <p className="text-xs text-graphite-500">Draw the ground of the restricted area. People count as inside where their feet are, vehicles where their wheels are. Add the no-people and no-vehicles rules on the Rules page.</p>
              ) : null}
              {zoneType === "HANDWASH_STATION" ? (
                <p className="text-xs text-graphite-500">Draw around the sink, seen from a camera above it, where hands are washed. A wash starts when hands show up inside. Add the WHO hand-washing rule on the Rules page.</p>
              ) : null}
              <div className="text-xs text-graphite-500">
                {points.length} points. Click or tap the corners in order around the area. Any number of corners works.
                {editing ? " The dashed outline is the current shape. Its rules and past incidents stay linked." : ""}
              </div>
              {referenceId ? (
                <Checkbox
                  checked={follow}
                  onChange={setFollow}
                  label="Follow camera moves"
                  hint={
                    follow
                      ? "The zone remembers this frame. If the camera moves a little it follows; if the view changes too much it pauses."
                      : "The zone stays exactly where it is drawn, even if the camera moves, and is always checked. Suits a fixed camera, or a video that changes scene."
                  }
                />
              ) : (
                <div className="text-xs text-graphite-500">No camera frame to remember yet. Zones saved now stay where they are drawn even if the camera moves.</div>
              )}
              <div className="flex gap-2">
                <GhostButton type="button" onClick={() => setPoints((current) => current.slice(0, -1))}>Undo</GhostButton>
                <GhostButton type="button" onClick={() => setPoints([])}>Clear</GhostButton>
              </div>
              <div className="flex gap-2">
                <PrimaryButton type="button" disabled={points.length < 3} onClick={save}>{editing ? "Save new shape" : "Save zone"}</PrimaryButton>
                {editing ? <GhostButton type="button" onClick={stopRedraw}>Cancel</GhostButton> : null}
              </div>
            </div>
          ) : <p className="text-sm text-graphite-600">Viewers can see zones. An admin draws them.</p>}
          <div className="panel p-5">
            <h2 className="text-sm font-semibold">Saved zones</h2>
            <ul className="mt-2 space-y-2 text-sm">
              {zones.map((zone) => (
                <li key={zone.id} className={`flex items-center justify-between gap-2 ${zone.id === editing?.id ? "rounded bg-brand-50 px-2 py-1 ring-1 ring-inset ring-brand-200" : ""}`}>
                  <span>
                    {zone.name}
                    <span className="block text-xs text-graphite-500">{ZONE_LABELS[zone.zone_type] || zone.zone_type} · {zone.polygon.length} corners</span>
                    <span className="block text-xs text-graphite-500">{zone.reference_key ? `Follows camera moves · View ${viewNumbers.get(zone.reference_key)}` : "Not linked to a camera view"}</span>
                  </span>
                  {admin ? (
                    <span className="flex flex-wrap justify-end gap-x-3">
                      <button className="link p-0 text-xs" onClick={() => startRedraw(zone)}>Redraw</button>
                      {referenceId ? (
                        <button className="link p-0 text-xs" title="Use when the zone already matches this frame. Zones locked together form one view." onClick={() => setView(zone, referenceId)}>Lock to this view</button>
                      ) : null}
                      {zone.reference_key ? (
                        <button className="link p-0 text-xs" title="Keep the zone where it is drawn. It stops following camera moves and never pauses." onClick={() => setView(zone, null)}>Unlink</button>
                      ) : null}
                      <button className="p-0 text-xs font-semibold text-danger-700 hover:text-danger-800" onClick={() => api(`/api/zones/${zone.id}`, { method: "DELETE" }).then(() => { if (zone.id === editing?.id) stopRedraw(); loadZones(); })}>Delete</button>
                    </span>
                  ) : null}
                </li>
              ))}
              {zones.length === 0 ? <li className="text-graphite-500">No zones yet.</li> : null}
            </ul>
          </div>
        </div>
      </div>
    </Shell>
  );
}
