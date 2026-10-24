export const EVENT_LABELS: Record<string, string> = {
  HELMET_VIOLATION: "Missing helmet",
  CLOTHING_VIOLATION: "Missing protective clothing",
  SHOES_VIOLATION: "Missing safety shoes",
  MASK_VIOLATION: "Missing mask",
  RESTRICTED_AREA_INTRUSION: "Person in restricted area",
  VEHICLE_IN_RESTRICTED_AREA: "Vehicle in restricted area",
  MACHINE_DANGER_ZONE_INTRUSION: "Machine danger zone",
  PEDESTRIAN_IN_FORKLIFT_ZONE: "Pedestrian in forklift lane",
  HANDWASH_INCOMPLETE: "Hand wash incomplete",
};

export const ZONE_LABELS: Record<string, string> = {
  PPE_ZONE: "PPE required area",
  RESTRICTED_AREA: "Restricted area",
  MACHINE_DANGER_ZONE: "Machine danger zone",
  FORKLIFT_LANE: "Forklift lane",
  PRODUCTION_ZONE: "Production zone",
  PACKING_ZONE: "Packing zone",
  HANDWASH_STATION: "Hand-wash station",
};

export const STATUS_LABELS: Record<string, string> = {
  NEW: "New",
  CONFIRMED: "Confirmed",
  FALSE_POSITIVE: "False positive",
  RESOLVED: "Resolved",
  ONLINE: "Online",
  OFFLINE: "Offline",
  AI_PROCESSING: "AI processing",
  DISABLED: "Disabled",
};

export const CONDITION_LABELS: Record<string, string> = {
  PERSON_INSIDE: "Person inside zone",
  VEHICLE_INSIDE: "Vehicle inside zone, forklifts allowed",
  HELMET_MISSING: "Helmet missing",
  CLOTHING_MISSING: "Protective clothing missing",
  SHOES_MISSING: "Safety shoes missing",
  MASK_MISSING: "Mask missing",
  HANDWASH_STEPS_MISSING: "WHO hand-washing steps missing",
};

export function eventLabel(value: string) {
  return EVENT_LABELS[value] || value;
}

export function formatWhen(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Ho_Chi_Minh",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function percent(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

const FACTORY_TZ = "Asia/Ho_Chi_Minh";

// "23:31:04", factory time.
export function formatTime(value?: string | Date | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: FACTORY_TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(date);
}

// "14 Oct", factory time.
export function formatDay(value?: string | Date | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", { timeZone: FACTORY_TZ, day: "2-digit", month: "short" }).format(date);
}

// "14 Oct 2026", factory time.
export function formatDate(value: Date) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: FACTORY_TZ, day: "2-digit", month: "short", year: "numeric" }).format(value);
}

export function shortId(id: string) {
  return `INC-${id.replace(/-/g, "").slice(0, 6).toUpperCase()}`;
}
