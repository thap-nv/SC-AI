"use client";

import { useEffect, useState } from "react";
import { imageUrl } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/labels";

const TONES: Record<string, string> = {
  slate: "bg-well text-graphite-600",
  green: "bg-success-50 text-success-700",
  red: "bg-brand-50 text-brand-700",
  amber: "bg-warn-50 text-warn-700",
  blue: "bg-info-50 text-info-700",
};

export function Badge({ value, tone = "slate" }: { value: string; tone?: string }) {
  return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${TONES[tone] || TONES.slate}`}>{value}</span>;
}

// Severity: bg/fg for the tag, bar for chart marks, hud for boxes drawn over a camera frame (white text sits on it).
export const SEVERITY: Record<string, { tag: string; bar: string; hud: string }> = {
  CRITICAL: { tag: "bg-brand-50 text-brand-700", bar: "#EE0033", hud: "#D1002D" },
  HIGH: { tag: "bg-warn-50 text-warn-700", bar: "#F78F24", hud: "#B85800" },
  MEDIUM: { tag: "bg-[#FFF6D6] text-[#765700]", bar: "#E0AE00", hud: "#8F6B00" },
  LOW: { tag: "bg-[#EEF0F2] text-[#4A5259]", bar: "#8A939B", hud: "#5F6870" },
};

export function SeverityTag({ severity }: { severity: string }) {
  const style = SEVERITY[severity] || SEVERITY.LOW;
  return <span className={`inline-flex rounded px-2 py-0.5 text-[10.5px] font-bold tracking-[0.06em] ${style.tag}`}>{severity}</span>;
}

const STATUS_STYLE: Record<string, string> = {
  NEW: "bg-info-50 text-info-700",
  CONFIRMED: "bg-brand-50 text-brand-700",
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
export function Kpi({ label, value, unit, hint, dark = false, critical = false }: { label: string; value: React.ReactNode; unit?: string; hint?: string; dark?: boolean; critical?: boolean }) {
  const number = dark ? "text-white" : critical ? "text-brand-600" : "text-graphite-900";
  return (
    <div className={`flex min-h-[138px] flex-col gap-2 p-5 ${dark ? "panel-dark" : "panel"}`}>
      <div className="flex items-center gap-2">
        <Marker className={dark ? "bg-brand-400" : critical ? "bg-brand-500" : "bg-graphite-300"} />
        <span className={`text-[13px] font-medium ${dark ? "text-fog-300" : "text-graphite-500"}`}>{label}</span>
      </div>
      <div className={`font-display text-[38px] font-bold leading-none tracking-[-0.02em] ${number}`}>
        {value}
        {unit ? <span className={`text-2xl font-semibold ${dark ? "text-fog-500" : "text-graphite-400"}`}>{unit}</span> : null}
      </div>
      {hint ? <div className={`text-[13px] ${dark ? "text-fog-500" : "text-graphite-500"}`}>{hint}</div> : null}
    </div>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border-l-2 border-brand-500 bg-brand-50 px-3 py-2 text-sm text-brand-700">{children}</p>;
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border-l-2 border-success-600 bg-success-50 px-3 py-2 text-sm text-success-900">{children}</p>;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

export function PrimaryButton(props: ButtonProps) {
  return <button {...props} className={`bg-brand-500 px-[18px] py-[11px] font-semibold text-white hover:bg-brand-600 disabled:opacity-50 ${props.className || ""}`} />;
}

export function OutlineButton(props: ButtonProps) {
  return <button {...props} className={`border border-brand-500 bg-transparent px-[18px] py-[10px] font-semibold text-brand-600 hover:bg-brand-50 disabled:opacity-50 ${props.className || ""}`} />;
}

export function GhostButton(props: ButtonProps) {
  return <button {...props} className={`border border-line-strong bg-surface font-semibold text-graphite-800 hover:bg-muted disabled:opacity-50 ${props.className || ""}`} />;
}

// A deeper red than PrimaryButton, so "Confirm violation" stays distinct when both sit side by side.
export function DangerButton(props: ButtonProps) {
  return <button {...props} className={`bg-brand-700 font-semibold text-white hover:bg-brand-800 disabled:opacity-50 ${props.className || ""}`} />;
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
          className={`whitespace-nowrap rounded-[7px] px-3.5 py-[7px] text-[13px] font-semibold ${value === option.value ? "bg-surface text-brand-600 shadow-[0_1px_2px_rgba(37,37,37,.14)]" : "text-graphite-500 hover:text-graphite-800"}`}
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
  return <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-brand-400 motion-safe:animate-rec" aria-hidden="true" />;
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

// A red pill on a hairline, after the active slide indicator on viettelidc.com.vn.
export function Rule({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 ${className}`} aria-hidden="true">
      <span className="h-[3px] w-10 rounded-full bg-brand-500" />
      <span className="h-px flex-1 bg-gradient-to-r from-line-strong to-transparent" />
    </div>
  );
}

// Paths copied from viettelidc.com.vn/assets/images/logo-IDC.svg (94 × 35).
const WORDMARK = [
  "M21.75 3.89H20.18C19.56 3.89 19.05 4.4 19.05 5.02V16.62C19.05 17.24 19.56 17.75 20.18 17.75H21.75C22.37 17.75 22.88 17.24 22.88 16.62V5.02C22.88 4.39 22.37 3.89 21.75 3.89Z",
  "M16.12 3.89C15.13 3.89 14.3 4.48 13.9 5.33L9.74 14.17C9.64 14.38 9.45 14.72 9.28 14.72C9.12 14.72 8.92 14.38 8.82 14.17L4.64 5.32C4.24 4.47 3.41 3.88 2.42 3.88H0L6.6 16.67C7.25 17.93 8.59 17.9 9.28 17.9C10.23 17.9 11.34 17.85 11.93 16.67L18.53 3.88H16.12V3.89Z",
  "M89.06 1.76C89.06 1.14 88.55 0.63 87.93 0.63H86.37C85.75 0.63 85.24 1.14 85.24 1.76V13.22C85.24 14.97 85.86 15.99 86.97 16.72C88.05 17.43 89.29 17.74 91.61 17.74H92.87C93.49 17.74 94 17.23 94 16.61V15.39H93.05C92.36 15.39 90.92 15.36 90.08 14.79C88.97 14.06 89.07 12.75 89.07 11.81V1.76H89.06Z",
  "M64.58 15.39C63.89 15.39 62.46 15.36 61.61 14.79C60.5 14.06 60.6 12.75 60.6 11.81V6.24H64.31C64.93 6.24 65.44 5.73 65.44 5.11V3.89H60.6V1.76C60.6 1.14 60.1 0.63 59.47 0.63H57.9C57.28 0.63 56.77 1.14 56.77 1.76V3.88H48.8V1.76C48.8 1.14 48.3 0.63 47.67 0.63H46.1C45.48 0.63 44.97 1.14 44.97 1.76V3.88H42.59V5.1C42.59 5.72 43.09 6.23 43.72 6.23H44.98V13.21C44.98 14.96 45.6 15.98 46.71 16.71C47.79 17.42 49.03 17.73 51.35 17.73H52.61C53.23 17.73 53.74 17.22 53.74 16.6V15.38H52.79C52.1 15.38 50.67 15.35 49.82 14.78C48.71 14.05 48.81 12.74 48.81 11.8V6.24H56.78V13.22C56.78 14.97 57.4 15.99 58.51 16.72C59.59 17.43 60.83 17.74 63.15 17.74H64.41C65.03 17.74 65.54 17.23 65.54 16.61V15.39H64.58Z",
  "M41.18 16.61V15.39H32.72C31.31 15.39 29.71 15.23 29.22 13.74C29.09 13.32 28.99 12.43 28.99 11.83H39.06C39.75 11.83 40.4 11.73 40.92 11.31C41.64 10.73 41.74 9.92 41.74 9.22C41.74 7.47 41.31 5.74 39.29 4.72C37.69 3.91 35.6 3.83 33.57 3.83C31.94 3.83 28.99 3.83 27.1 5.14C25.2 6.45 25.04 8.36 25.04 10.94C25.04 12.77 25.14 14.68 26.28 15.99C27.72 17.61 29.81 17.74 31.57 17.74H40.05C40.68 17.74 41.18 17.24 41.18 16.61ZM37.78 8.67C37.78 9.04 37.68 9.48 36.93 9.48H31.5C30.12 9.48 29 10.11 29 10.89V9.48C29.03 8.56 29 7.81 29.78 7.1C30.83 6.16 32.4 6.19 33.41 6.19C34.49 6.19 35.73 6.24 36.68 6.82C37.23 7.15 37.78 7.81 37.78 8.67Z",
  "M82.53 16.61V15.39H74.07C72.66 15.39 71.06 15.23 70.57 13.74C70.44 13.32 70.34 12.43 70.34 11.83H80.4C81.09 11.83 81.74 11.73 82.26 11.31C82.98 10.73 83.08 9.92 83.08 9.22C83.08 7.47 82.66 5.74 80.63 4.72C79.03 3.91 76.94 3.83 74.91 3.83C73.28 3.83 70.34 3.83 68.44 5.14C66.54 6.45 66.38 8.36 66.38 10.94C66.38 12.77 66.48 14.68 67.62 15.99C69.06 17.61 71.15 17.74 72.91 17.74H81.39C82.02 17.74 82.53 17.24 82.53 16.61ZM79.13 8.67C79.13 9.04 79.03 9.48 78.28 9.48H72.84C71.46 9.48 70.34 10.11 70.34 10.89V9.48C70.37 8.56 70.34 7.81 71.12 7.1C72.17 6.16 73.73 6.19 74.75 6.19C75.83 6.19 77.07 6.24 78.02 6.82C78.57 7.15 79.13 7.81 79.13 8.67Z",
  "M21.75 0.01H20.18C19.56 0.01 19.05 0.52 19.05 1.14V1.45V3.89H19.07C19.18 3.25 19.9 2.58 20.97 2.58H21.75C22.37 2.58 22.88 2.07 22.88 1.45V1.14C22.88 0.51 22.38 0.01 21.75 0.01Z",
];

const IDC = [
  "M72.13 25.16H70.12V34.42H72.13V25.16Z",
  "M79.9 34.42H75.5C74.47 34.42 73.95 33.96 73.95 33.03V26.55C73.95 25.62 74.47 25.16 75.5 25.16H79.62C80.32 25.16 80.93 25.25 81.45 25.43C81.97 25.61 82.37 25.85 82.67 26.13C82.97 26.42 83.21 26.77 83.39 27.19C83.57 27.61 83.68 28.03 83.74 28.43C83.8 28.83 83.82 29.28 83.82 29.79C83.82 30.28 83.79 30.73 83.74 31.14C83.68 31.54 83.57 31.96 83.41 32.38C83.24 32.8 83.02 33.16 82.74 33.44C82.46 33.73 82.08 33.96 81.6 34.14C81.11 34.33 80.55 34.42 79.9 34.42ZM78.93 26.55H76.73C76.43 26.55 76.22 26.59 76.12 26.68C76.02 26.77 75.97 26.94 75.97 27.21V32.37C75.97 32.63 76.02 32.81 76.12 32.9C76.22 32.99 76.42 33.03 76.73 33.03H78.93C79.52 33.03 80 32.95 80.39 32.8C80.78 32.65 81.06 32.41 81.26 32.09C81.45 31.77 81.58 31.44 81.66 31.08C81.73 30.73 81.77 30.3 81.77 29.78C81.77 29.27 81.73 28.84 81.66 28.48C81.59 28.13 81.46 27.79 81.26 27.47C81.07 27.15 80.78 26.92 80.39 26.76C80 26.63 79.51 26.55 78.93 26.55Z",
  "M94 34.42H89.56C88.68 34.42 87.93 34.31 87.32 34.08C86.71 33.86 86.25 33.52 85.92 33.09C85.59 32.65 85.37 32.17 85.23 31.64C85.1 31.11 85.03 30.49 85.03 29.79C85.03 29.09 85.09 28.47 85.23 27.94C85.36 27.41 85.59 26.93 85.92 26.49C86.24 26.05 86.71 25.72 87.32 25.5C87.93 25.28 88.68 25.16 89.56 25.16H93.83V26.55H90.5C89.2 26.55 88.31 26.78 87.83 27.23C87.35 27.68 87.11 28.54 87.11 29.79C87.11 31.04 87.35 31.9 87.83 32.35C88.31 32.8 89.2 33.03 90.5 33.03H94V34.42Z",
];

// Viettel IDC logo: the red "viettel" wordmark takes `accent`, "IDC" takes currentColor. Pass accent="currentColor" for a one-colour logo.
export function Logo({ className = "", accent = "#EE0033" }: { className?: string; accent?: string }) {
  return (
    <svg viewBox="0 0 94 35" className={className} role="img" aria-label="Viettel IDC">
      <g fill={accent}>{WORDMARK.map((d) => <path key={d} d={d} />)}</g>
      <g fill="currentColor">{IDC.map((d) => <path key={d} d={d} />)}</g>
    </svg>
  );
}
