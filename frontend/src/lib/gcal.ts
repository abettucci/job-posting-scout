function toGCalDate(iso: string): string {
  // "2025-04-15T14:00:00" → "20250415T140000"
  return iso.replace(/[-:]/g, "").split(".")[0];
}

function addMinutes(iso: string, minutes: number): string {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() + minutes);
  return d.toISOString();
}

export function gcalUrl(params: {
  title: string;
  startIso: string;
  durationMinutes?: number;
  location?: string;
  details?: string;
}): string {
  const { title, startIso, durationMinutes = 60, location, details } = params;
  const start = toGCalDate(startIso);
  const end = toGCalDate(addMinutes(startIso, durationMinutes));

  const qs = new URLSearchParams({
    text: title,
    dates: `${start}/${end}`,
    ...(location ? { location } : {}),
    ...(details ? { details } : {}),
  });

  return `https://calendar.google.com/calendar/r/eventedit?${qs.toString()}`;
}
