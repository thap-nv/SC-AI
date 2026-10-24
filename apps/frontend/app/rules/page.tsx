"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useApp } from "@/components/providers";
import Shell from "@/components/shell";
import { ErrorText, SeverityTag, Switch } from "@/components/ui";
import { api, getUser, Rule, Zone } from "@/lib/api";
import { CONDITION_LABELS, eventLabel, ZONE_LABELS } from "@/lib/labels";

const TEMPLATES = [
  { label: "Helmet required", event_type: "HELMET_VIOLATION", condition_type: "HELMET_MISSING", severity: "HIGH", min_duration_s: 2 },
  { label: "Protective clothing required", event_type: "CLOTHING_VIOLATION", condition_type: "CLOTHING_MISSING", severity: "HIGH", min_duration_s: 2 },
  { label: "Mask required", event_type: "MASK_VIOLATION", condition_type: "MASK_MISSING", severity: "MEDIUM", min_duration_s: 2 },
  { label: "Restricted area: no people", event_type: "RESTRICTED_AREA_INTRUSION", condition_type: "PERSON_INSIDE", severity: "HIGH", min_duration_s: 1 },
  { label: "Restricted area: no vehicles except forklifts", event_type: "VEHICLE_IN_RESTRICTED_AREA", condition_type: "VEHICLE_INSIDE", severity: "HIGH", min_duration_s: 1 },
  { label: "Machine danger zone", event_type: "MACHINE_DANGER_ZONE_INTRUSION", condition_type: "PERSON_INSIDE", severity: "CRITICAL", min_duration_s: 1 },
  { label: "Forklift lane", event_type: "PEDESTRIAN_IN_FORKLIFT_ZONE", condition_type: "PERSON_INSIDE", severity: "CRITICAL", min_duration_s: 1 },
  { label: "WHO 6-step hand washing", event_type: "HANDWASH_INCOMPLETE", condition_type: "HANDWASH_STEPS_MISSING", severity: "MEDIUM", min_duration_s: 1.5 },
];

export default function RulesPage() {
  const { toast } = useApp();
  const [rules, setRules] = useState<Rule[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [template, setTemplate] = useState(TEMPLATES[0].label);
  const [zoneId, setZoneId] = useState("");
  const [name, setName] = useState(TEMPLATES[0].label);
  const [seconds, setSeconds] = useState(2);
  const [cooldown, setCooldown] = useState(30);
  const [error, setError] = useState("");
  const [admin, setAdmin] = useState(false);
  // The rule the form is changing, or null while it makes a new one.
  const [editing, setEditing] = useState<Rule | null>(null);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => setAdmin(getUser()?.role === "ADMIN"), []);
  const chosen = TEMPLATES.find((item) => item.label === template) || TEMPLATES[0];
  const condition = editing ? editing.condition_type : chosen.condition_type;

  function load() {
    Promise.all([api<Rule[]>("/api/rules"), api<Zone[]>("/api/zones")])
      .then(([nextRules, nextZones]) => {
        setRules(nextRules);
        setZones(nextZones);
        if (!zoneId && nextZones[0]) setZoneId(nextZones[0].id);
      })
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    const timing = { min_duration_ms: Math.round(seconds * 1000), cooldown_ms: Math.round(cooldown * 1000) };
    try {
      if (editing) {
        await api(`/api/rules/${editing.id}`, { method: "PATCH", body: JSON.stringify({ name, ...timing }) });
        setEditing(null);
      } else {
        await api("/api/rules", {
          method: "POST",
          body: JSON.stringify({
            zone_id: zoneId,
            name,
            event_type: chosen.event_type,
            condition_type: chosen.condition_type,
            ...timing,
            grace_ms: 1000,
            severity: chosen.severity,
            enabled: true,
          }),
        });
      }
      toast(`Rule saved · ${name}`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the rule");
    }
  }

  function startEdit(rule: Rule) {
    setEditing(rule);
    setName(rule.name);
    setSeconds(rule.min_duration_ms / 1000);
    setCooldown(rule.cooldown_ms / 1000);
    // On a phone the form sits below the list.
    form.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function stopEdit() {
    setEditing(null);
    setName(chosen.label);
    setSeconds(chosen.min_duration_s);
    setCooldown(30);
  }

  async function setEnabled(rule: Rule, enabled: boolean) {
    setError("");
    try {
      await api(`/api/rules/${rule.id}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the rule");
    }
  }

  const label = "flex flex-col gap-1.5 text-[12.5px] text-fog-300";
  const toggle = (rule: Rule) =>
    admin ? <Switch size="sm" checked={rule.enabled} onChange={(next) => setEnabled(rule, next)} label={`${rule.enabled ? "Disable" : "Enable"} ${rule.name}`} /> : <span className="text-xs text-graphite-500">{rule.enabled ? "On" : "Off"}</span>;
  const edit = (rule: Rule) =>
    admin ? (
      <button type="button" onClick={() => startEdit(rule)} aria-label={`Edit ${rule.name}`} className="rounded px-2 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-50">
        Edit
      </button>
    ) : null;

  return (
    <Shell title="Rules">
      {error ? <ErrorText>{error}</ErrorText> : null}
      {/* Side by side on a wide screen; stacked, the rules come first and the form after them. */}
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
        {admin ? (
          <form ref={form} onSubmit={save} className="panel-dark order-last flex scroll-mt-4 flex-col gap-3.5 p-[22px] xl:order-none xl:w-[300px] xl:shrink-0">
            <h2 className="relative font-display text-lg font-bold text-white">{editing ? "Edit rule" : "New rule"}</h2>
            {editing ? (
              <p className="text-[12.5px] text-fog-300">{editing.camera_name} · {editing.zone_name} · {eventLabel(editing.event_type)}</p>
            ) : (
              <label className={label}>Template
                <select className="field-dark" value={template} onChange={(e) => { setTemplate(e.target.value); setName(e.target.value); const next = TEMPLATES.find((item) => item.label === e.target.value); if (next) setSeconds(next.min_duration_s); }}>
                  {TEMPLATES.map((item) => <option key={item.label}>{item.label}</option>)}
                </select>
              </label>
            )}
            <label className={label}>Name<input className="field-dark" value={name} onChange={(e) => setName(e.target.value)} required /></label>
            {editing ? null : (
              <label className={label}>Zone
                <select className="field-dark" value={zoneId} onChange={(e) => setZoneId(e.target.value)}>
                  {zones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name} · {ZONE_LABELS[zone.zone_type]}</option>)}
                </select>
              </label>
            )}
            <div className="grid grid-cols-2 gap-2.5">
              <label className={label}>{condition === "HANDWASH_STEPS_MISSING" ? "Min per step (s)" : "Min duration (s)"}<input className="field-dark" type="number" min={0} step={0.1} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} /></label>
              <label className={label}>Cooldown (s)<input className="field-dark" type="number" min={0} step={1} value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))} /></label>
            </div>
            <p className="text-xs leading-normal text-fog-500">
              {CONDITION_LABELS[condition]}.{" "}
              {condition === "PERSON_INSIDE"
                ? "Opens when a person's feet stay inside the zone for the minimum duration. Someone riding a vehicle, such as a forklift driver, is not counted."
                : condition === "VEHICLE_INSIDE"
                  ? "Opens when a car, truck, bus or motorcycle stays inside the zone. Forklifts are allowed. A vehicle whose type is not known yet does not raise an alert."
                  : condition === "HANDWASH_STEPS_MISSING"
                    ? "Checked once per wash, when the hands leave the sink. Each step must be seen for the minimum time; a step done with each hand needs half of it from each. Steps the model cannot recognise are never reported missing."
                    : "Only a clear “missing” result raises an alert. Unknown, such as a turned-away face or hidden feet, does not."}
            </p>
            {/* What the worker does with cooldown_ms: per person live, per rule on an uploaded video playing over (CameraLoop._quiet_until). */}
            <p className="text-xs leading-normal text-fog-500">
              {condition === "HANDWASH_STEPS_MISSING"
                ? "Cooldown: every wrong wash is reported. On an uploaded video playing over, at most one per cooldown, counted from the end of the last one reported."
                : "Cooldown: the same person or vehicle is not alerted again for this long after leaving. On an uploaded video playing over, the rule alerts at most once per cooldown."}{" "}
              0 turns the limit off.
            </p>
            <button type="submit" className="bg-brand-500 py-3 font-bold text-ink hover:bg-brand-300">{editing ? "Save changes" : "Save rule"}</button>
            {editing ? (
              <button type="button" onClick={stopEdit} className="py-1 text-sm font-semibold text-fog-300 hover:text-white">Cancel</button>
            ) : null}
          </form>
        ) : null}
        {/* Phone: one card per rule. */}
        <ul className="panel divide-y divide-line-soft md:hidden">
          {rules.map((rule) => (
            <li key={rule.id} className={`flex items-start gap-3 px-4 py-3.5 ${rule.enabled ? "" : "opacity-45"}`}>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="text-sm font-semibold">{rule.name}</div>
                <div className="text-[12.5px] text-graphite-500">{rule.camera_name} · {rule.zone_name}</div>
                <div className="text-[12.5px] text-graphite-600">{eventLabel(rule.event_type)}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2">
                  <SeverityTag severity={rule.severity} />
                  <span className="font-mono text-[11.5px] text-graphite-600">{rule.min_duration_ms / 1000}s · cd {rule.cooldown_ms / 1000}s</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {edit(rule)}
                {toggle(rule)}
              </div>
            </li>
          ))}
          {rules.length === 0 ? <li className="px-4 py-6 text-sm text-graphite-500">No rules yet.</li> : null}
        </ul>
        <div className="panel hidden min-w-0 overflow-auto md:block xl:flex-1">
          <table className="min-w-[760px]">
            <thead><tr><th>Rule</th><th>Zone</th><th>Violation</th><th>Timing</th><th>Severity</th><th className="text-right">On</th></tr></thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id} className={rule.enabled ? "" : "opacity-45"}>
                  <td>
                    <div className="text-sm font-semibold">{rule.name}</div>
                    <div className="text-xs text-graphite-400">{rule.camera_name}</div>
                  </td>
                  <td className="text-[13.5px]">{rule.zone_name}</td>
                  <td className="text-[13.5px]">{eventLabel(rule.event_type)}</td>
                  <td className="whitespace-nowrap font-mono text-xs text-graphite-600">{rule.min_duration_ms / 1000}s · cd {rule.cooldown_ms / 1000}s</td>
                  <td><SeverityTag severity={rule.severity} /></td>
                  <td>
                    <div className="flex items-center justify-end gap-1.5">
                      {edit(rule)}
                      {toggle(rule)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
