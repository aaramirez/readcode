// Per-browser preferences in localStorage. Storage can be unavailable (private
// mode, blocked site data), so every access is wrapped and falls back silently.

export type Theme = 'auto' | 'light' | 'dark';

const PREFIX = 'readcode:';

export function loadPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function savePref(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // ignore: preferences are a convenience only
  }
}
