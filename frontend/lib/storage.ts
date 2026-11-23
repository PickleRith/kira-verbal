// Browser storage for the demo session token and an unsent turn.
// Storage can be unavailable (private mode, blocked site data), so every access is guarded;
// the page still works for the current visit, it just cannot resume after a reload.

export interface PendingTurn {
  clientTurnId: string;
  questionId: string;
  transcript: string;
}

const tokenKey = (sessionId: string) => `kira-verbal:token:${sessionId}`;
const pendingKey = (sessionId: string) => `kira-verbal:pending:${sessionId}`;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // ignore: resume is a convenience, not a requirement
  }
}

export const sessionStore = {
  getToken: (sessionId: string) => read(tokenKey(sessionId)),
  setToken: (sessionId: string, token: string) => write(tokenKey(sessionId), token),

  // An answer that was sent but not confirmed keeps its client_turn_id, so resending it
  // after a network error or reload is recognised by the server as the same turn.
  getPending(sessionId: string): PendingTurn | null {
    const raw = read(pendingKey(sessionId));
    if (!raw) return null;
    try {
      return JSON.parse(raw) as PendingTurn;
    } catch {
      return null;
    }
  },
  setPending: (sessionId: string, pending: PendingTurn | null) =>
    write(pendingKey(sessionId), pending ? JSON.stringify(pending) : null),
};
