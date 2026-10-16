function fields(date: Date, timeZone: string) {
  return Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).formatToParts(date).map(part => [part.type, part.value]));
}

export function dateKey(date: Date, timeZone: string) {
  const value = fields(date, timeZone);
  return `${value.year.padStart(4, "0")}-${value.month}-${value.day}`;
}

export function dateTimeLocal(date: Date, timeZone: string) {
  const value = fields(date, timeZone);
  return `${value.year.padStart(4, "0")}-${value.month}-${value.day}T${value.hour}:${value.minute}`;
}

export function shiftDate(day: string, days: number) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function startOfWeek(day: string) {
  return shiftDate(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7));
}

export function prettyDate(date: Date | string, timeZone: string, options: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat("ru-RU", { ...options, timeZone: typeof date === "string" ? "UTC" : timeZone })
    .format(typeof date === "string" ? new Date(`${date}T12:00:00Z`) : date);
}

export function dayStart(day: string, timeZone: string) {
  const wall = Date.parse(`${day}T00:00:00Z`);
  let low = wall - 36 * 3_600_000;
  let high = wall + 36 * 3_600_000;
  const formatter = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
  // Find the first instant of the civil date, including midnight clock changes.
  while (high - low > 1) {
    const middle = Math.floor((low + high) / 2);
    const value = Object.fromEntries(formatter.formatToParts(new Date(middle)).map(part => [part.type, part.value]));
    const key = `${value.year.padStart(4, "0")}-${value.month}-${value.day}`;
    if (key < day) low = middle;
    else high = middle;
  }
  return new Date(high);
}

export function localInstants(value: string, timeZone: string, original?: string) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return [];
  const wall = Date.parse(`${value}:00Z`);
  if (!Number.isFinite(wall) || new Date(wall).toISOString().slice(0, 16) !== value) return [];
  const offsets = new Set<number>();
  for (const hours of [-36, -12, 0, 12, 36]) {
    const instant = new Date(wall + hours * 3_600_000);
    const part = fields(instant, timeZone);
    offsets.add(Date.parse(`${part.year.padStart(4, "0")}-${part.month}-${part.day}T${part.hour}:${part.minute}:${part.second}Z`) - instant.getTime());
  }
  const candidates = [...offsets].map(offset => new Date(wall - offset))
    .filter(date => dateTimeLocal(date, timeZone) === value).sort((a, b) => a.getTime() - b.getTime());
  return candidates.map(date => original && dateTimeLocal(new Date(original), timeZone) === value &&
    Math.abs(date.getTime() - Date.parse(original)) < 60_000 ? new Date(original).toISOString() : date.toISOString());
}

export function resolveLocalTime(value: string, timeZone: string, choice: string, original?: string) {
  const candidates = localInstants(value, timeZone, original);
  if (!candidates.length) throw new Error(`Это время не существует в часовом поясе ${timeZone}. Выберите другое время.`);
  if (candidates.length === 1) return candidates[0];
  if (candidates.includes(choice)) return choice;
  throw new Error("Это время повторяется при переводе часов. Выберите смещение часового пояса.");
}
