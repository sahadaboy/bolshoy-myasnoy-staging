const KEY = 'bolshoy-myasnoy.checkout.v1';
let memory: { fingerprint: string; id: string } | null = null;

/** Reuse a key after network failure/reload, without storing contact details. */
export async function orderRequestId(payload: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const fingerprint = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (
      stored &&
      typeof stored.id === 'string' &&
      /^[a-f0-9-]{36}$/i.test(stored.id) &&
      stored.fingerprint === fingerprint
    )
      return stored.id;
  } catch {
    /* In-memory retry still works when storage is unavailable. */
  }
  if (memory?.fingerprint === fingerprint) return memory.id;
  memory = { fingerprint, id: crypto.randomUUID() };
  try {
    localStorage.setItem(KEY, JSON.stringify(memory));
  } catch {
    /* Optional durability. */
  }
  return memory.id;
}
export function finishOrderRequest() {
  memory = null;
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* Storage can be unavailable in private mode. */
  }
}
