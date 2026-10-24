"use client";

import { useEffect, useState } from "react";
import { imageUrl } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/labels";

const TONES: Record<string, string> = {
  slate: "bg-well text-graphite-600",
  green: "bg-success-50 text-success-700",
  red: "bg-danger-50 text-danger-700",
  amber: "bg-warn-50 text-warn-700",
  blue: "bg-info-50 text-info-700",
};

export function Badge({ value, tone = "slate" }: { value: string; tone?: string }) {
  return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${TONES[tone] || TONES.slate}`}>{value}</span>;
}

// Severity: bg/fg for the tag, bar for chart marks, hud for boxes drawn over a camera frame (white text sits on it).
export const SEVERITY: Record<string, { tag: string; bar: string; hud: string }> = {
  CRITICAL: { tag: "bg-danger-50 text-danger-700", bar: "#D4183D", hud: "#B3122F" },
  HIGH: { tag: "bg-warn-50 text-warn-700", bar: "#F78F24", hud: "#B85800" },
  MEDIUM: { tag: "bg-[#FFF6D6] text-[#765700]", bar: "#E0AE00", hud: "#8F6B00" },
  LOW: { tag: "bg-[#EDF1F6] text-[#475569]", bar: "#7F8DA1", hud: "#5A677B" },
};

export function SeverityTag({ severity }: { severity: string }) {
  const style = SEVERITY[severity] || SEVERITY.LOW;
  return <span className={`inline-flex rounded px-2 py-0.5 text-[10.5px] font-bold tracking-[0.06em] ${style.tag}`}>{severity}</span>;
}

const STATUS_STYLE: Record<string, string> = {
  NEW: "bg-info-50 text-info-700",
  CONFIRMED: "bg-danger-50 text-danger-700",
  FALSE_POSITIVE: "bg-well text-graphite-600",
  RESOLVED: "bg-success-50 text-success-700",
  ONLINE: "bg-success-50 text-success-700",
  AI_PROCESSING: "bg-success-50 text-success-700",
  OFFLINE: "bg-well text-graphite-500",
  DISABLED: "bg-well text-graphite-500",
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLE[status] || STATUS_STYLE.DISABLED}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {label || STATUS_LABELS[status] || status}
    </span>
  );
}

export function Marker({ className = "bg-brand-500" }: { className?: string }) {
  return <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${className}`} aria-hidden="true" />;
}

// KPI tile. The dark variant leads a row; the critical variant marks the critical count in red.
// Smaller on a phone, where the tiles sit two to a row.
export function Kpi({ label, value, unit, hint, dark = false, critical = false, className = "" }: { label: string; value: React.ReactNode; unit?: string; hint?: string; dark?: boolean; critical?: boolean; className?: string }) {
  const number = dark ? "text-white" : critical ? "text-danger-600" : "text-graphite-900";
  return (
    <div className={`flex min-h-[112px] flex-col gap-2 p-4 md:min-h-[138px] md:p-5 ${dark ? "panel-dark" : "panel"} ${className}`}>
      <div className="flex items-center gap-2">
        <Marker className={dark ? "bg-brand-400" : critical ? "bg-danger-500" : "bg-graphite-300"} />
        <span className={`text-[12.5px] font-medium md:text-[13px] ${dark ? "text-fog-300" : "text-graphite-500"}`}>{label}</span>
      </div>
      <div className={`font-display text-[30px] font-bold leading-none tracking-[-0.02em] md:text-[38px] ${number}`}>
        {value}
        {unit ? <span className={`text-xl font-semibold md:text-2xl ${dark ? "text-fog-500" : "text-graphite-400"}`}>{unit}</span> : null}
      </div>
      {hint ? <div className={`text-xs md:text-[13px] ${dark ? "text-fog-500" : "text-graphite-500"}`}>{hint}</div> : null}
    </div>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border-l-2 border-danger-500 bg-danger-50 px-3 py-2 text-sm text-danger-700">{children}</p>;
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border-l-2 border-success-600 bg-success-50 px-3 py-2 text-sm text-success-900">{children}</p>;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

// Cyan with navy text, as on the site: white text on the cyan would not read.
export function PrimaryButton(props: ButtonProps) {
  return <button {...props} className={`bg-brand-500 px-[18px] py-[11px] font-semibold text-ink hover:bg-brand-300 disabled:opacity-50 ${props.className || ""}`} />;
}

export function OutlineButton(props: ButtonProps) {
  return <button {...props} className={`border border-brand-500 bg-transparent px-[18px] py-[10px] font-semibold text-brand-600 hover:bg-brand-50 disabled:opacity-50 ${props.className || ""}`} />;
}

export function GhostButton(props: ButtonProps) {
  return <button {...props} className={`border border-line-strong bg-surface font-semibold text-graphite-800 hover:bg-muted disabled:opacity-50 ${props.className || ""}`} />;
}

// Red, for "Confirm violation": the one action that marks a person as breaking a rule.
export function DangerButton(props: ButtonProps) {
  return <button {...props} className={`bg-danger-600 font-semibold text-white hover:bg-danger-700 disabled:opacity-50 ${props.className || ""}`} />;
}

export function Switch({ checked, onChange, label, size = "md", tone = "success", disabled }: { checked: boolean; onChange: (next: boolean) => void; label: string; size?: "md" | "sm"; tone?: "success" | "brand"; disabled?: boolean }) {
  const track = size === "md" ? "h-[26px] w-[46px]" : "h-[22px] w-10";
  const knob = size === "md" ? "h-5 w-5" : "h-4 w-4";
  const on = tone === "success" ? "bg-success-600" : "bg-brand-500";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        event.preventDefault();
        onChange(!checked);
      }}
      className={`flex shrink-0 rounded-full p-[3px] transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${track} ${checked ? `justify-end ${on}` : "justify-start bg-toggle"}`}
    >
      <span className={`rounded-full bg-surface shadow-[0_1px_3px_rgba(0,0,0,.25)] ${knob}`} />
    </button>
  );
}

// A checkbox with a label and an optional hint, drawn as a button: a native box would pick up the full-width input style.
export function Checkbox({ checked, onChange, label, hint }: { checked: boolean; onChange: (next: boolean) => void; label: string; hint?: React.ReactNode }) {
  return (
    <button type="button" role="checkbox" aria-checked={checked} onClick={() => onChange(!checked)} className="flex items-start gap-3 rounded-none bg-transparent p-0 text-left font-normal text-graphite-800">
      <span className={`mt-px grid h-[18px] w-[18px] shrink-0 place-items-center rounded border-[1.5px] text-xs font-bold text-ink ${checked ? "border-brand-500 bg-brand-500" : "border-line-strong bg-surface"}`}>{checked ? "✓" : ""}</span>
      <span className="flex flex-col gap-[3px]">
        <span className="text-[13.5px] font-semibold">{label}</span>
        {hint ? <span className="text-xs leading-normal text-graphite-500">{hint}</span> : null}
      </span>
    </button>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T; onChange: (next: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex max-w-full gap-0.5 overflow-x-auto rounded-[9px] bg-well p-[3px]">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={`whitespace-nowrap rounded-[7px] px-2.5 py-[7px] text-[13px] font-semibold sm:px-3.5 ${value === option.value ? "bg-surface text-brand-600 shadow-[0_1px_2px_rgba(10,21,37,.14)]" : "text-graphite-500 hover:text-graphite-800"}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function LiveDot({ demo = false }: { demo?: boolean }) {
  const style = demo ? "bg-amber-500 motion-safe:animate-demo-pulse" : "bg-success-600 motion-safe:animate-live-pulse";
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${style}`} aria-hidden="true" />;
}

export function RecDot() {
  return <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-danger-400 motion-safe:animate-rec" aria-hidden="true" />;
}

// An image from the API (it needs the bearer token, so it is fetched as a blob). Striped placeholder until it loads.
export function Snapshot({ path, alt, placeholder, refreshMs, className = "" }: { path: string; alt: string; placeholder: string; refreshMs?: number; className?: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let alive = true;
    let current = "";
    const load = () =>
      imageUrl(path)
        .then((url) => {
          if (!alive) return URL.revokeObjectURL(url);
          if (current) URL.revokeObjectURL(current);
          current = url;
          setSrc(url);
        })
        .catch(() => undefined);
    load();
    const timer = refreshMs ? setInterval(load, refreshMs) : undefined;
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
      if (current) URL.revokeObjectURL(current);
    };
  }, [path, refreshMs]);
  if (src) return <img src={src} alt={alt} className={`object-cover ${className}`} />;
  return <div className={`grid place-items-center bg-stripes font-mono text-[11.5px] text-fog-500 ${className}`}>{placeholder}</div>;
}

// A pill in the brand gradient on a hairline, after the gradient accents on madison-technologies.com.
export function Rule({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 ${className}`} aria-hidden="true">
      <span className="h-[3px] w-10 rounded-full bg-brand-text" />
      <span className="h-px flex-1 bg-gradient-to-r from-line-strong to-transparent" />
    </div>
  );
}

// Path copied from madison-technologies.com/madison-assets/logos/madison/madison-logo.svg (121 × 113).
const MARK = "M91.2423 112.079L120.358 112.268L92.8806 39.0047L78.8493 27.6463L94.3098 37.6426L100.129 52.4804L115.784 42.647L115.781 40.7782L110.286 38.7469L115.857 39.597L115.775 35.96L108.372 28.3973L102.294 25.8666L108.106 27.0819L107.811 20.2974L96.2553 10.428L87.5767 0L67.7663 18.6741L67.735 18.6488L55.5913 18.5054L40.6515 42.6799L45.7248 31.1284L26.7974 31.4548L6.50403 51.2946L0 111.893L32.2903 112.079L26.9406 106.319L20.6832 108.48L26.9376 105.031L29.6595 74.5281L23.6753 68.5239L47.4809 81.8375L66.2655 69.3973L60.452 58.7349L93.9192 105.08L99.4357 108.124L94.325 106.36L91.2423 112.079Z";

// The cyan mark alone, for the phone top bar.
export function Mark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 121 113" className={`w-auto shrink-0 text-brand-500 ${className}`} aria-hidden="true">
      <path d={MARK} fill="currentColor" />
    </svg>
  );
}

// Madison Technologies lockup, as in the site header: cyan mark, "MADISON" in the brand gradient, "TECHNOLOGIES" in grey.
// Sized by font size (className="text-[15px]"). Pass light on a white surface, where the gradient would fade: "MADISON" turns navy.
export function Logo({ className = "", light = false }: { className?: string; light?: boolean }) {
  return (
    <span role="img" aria-label="Madison Technologies" className={`inline-flex items-center gap-[0.55em] leading-none ${className}`}>
      <Mark className="h-[2.2em]" />
      <span className="flex flex-col gap-[0.35em]" aria-hidden="true">
        <span className={`font-bold tracking-[0.32em] ${light ? "text-ink" : "bg-brand-text bg-clip-text text-transparent"}`}>MADISON</span>
        <span className={`text-[0.62em] font-medium tracking-[0.24em] ${light ? "text-graphite-500" : "text-fog-300"}`}>TECHNOLOGIES</span>
      </span>
    </span>
  );
}
