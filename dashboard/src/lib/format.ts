/** Format an ISO timestamp for display; returns the raw input if it is unparseable. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 60 * 60 * 24 * 365],
  ["month", 60 * 60 * 24 * 30],
  ["day", 60 * 60 * 24],
  ["hour", 60 * 60],
  ["minute", 60],
  ["second", 1],
];

/** "3 hours ago" / "in 2 days"; returns the raw input if it is unparseable. */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;

  const deltaSeconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (Math.abs(deltaSeconds) >= secondsPerUnit || unit === "second") {
      return formatter.format(Math.round(deltaSeconds / secondsPerUnit), unit);
    }
  }
  return formatter.format(0, "second");
}

/** Render a fractional threshold as "0.1 (10%)" so its meaning is unambiguous. */
export function formatFraction(value: number): string {
  const percent = value * 100;
  const percentText = Number.isInteger(percent)
    ? String(percent)
    : String(Number(percent.toFixed(4)));
  return `${value} (${percentText}%)`;
}

/** First 8 characters of an id, for compact display of an unresolved reference. */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}
