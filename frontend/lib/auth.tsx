"use client";

// Signed-in user state for the whole app. The server is the authority: on load the stored
// token is checked with GET /v1/me, and an expired or revoked token is dropped.

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api } from "./api";
import { authStore } from "./storage";
import type { Me, RegisterRequest, Role } from "./types";

interface AuthState {
  user: Me | null;
  token: string | null;
  ready: boolean; // false until the stored token has been checked
  login: (email: string, password: string) => Promise<Me>;
  register: (body: RegisterRequest) => Promise<Me>;
  logout: () => Promise<void>;
  setUser: (user: Me) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function homeFor(role: Role) {
  return role === "teacher" ? "/teacher" : "/student";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = authStore.getToken();
    if (!stored) {
      setReady(true);
      return;
    }
    api
      .me(stored)
      .then((me) => {
        setUser(me);
        setToken(stored);
      })
      .catch((e: unknown) => {
        // Only forget the token when the server says it is no good, not on a network blip.
        if (e instanceof ApiError && e.status === 401) authStore.setToken(null);
      })
      .finally(() => setReady(true));
  }, []);

  const adopt = useCallback((next: { token: string; user: Me }) => {
    authStore.setToken(next.token);
    setToken(next.token);
    setUser(next.user);
    return next.user;
  }, []);

  const login = useCallback(
    async (email: string, password: string) => adopt(await api.login(email, password)),
    [adopt],
  );
  const register = useCallback(async (body: RegisterRequest) => adopt(await api.register(body)), [adopt]);

  const logout = useCallback(async () => {
    const current = token;
    authStore.setToken(null);
    setToken(null);
    setUser(null);
    if (current) {
      try {
        await api.logout(current);
      } catch {
        // already signed out locally; the server token expires on its own
      }
    }
  }, [token]);

  const value = useMemo(
    () => ({ user, token, ready, login, register, logout, setUser }),
    [user, token, ready, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

// For pages that need a signed-in user with a given role. Sends everyone else to the
// right place: signed out -> /login, wrong role -> their own home.
export function useRequireRole(role: Role): { user: Me; token: string } | null {
  const { user, token, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!user) {
      const next = typeof window !== "undefined" ? window.location.pathname : "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    } else if (user.role !== role) {
      router.replace(homeFor(user.role));
    }
  }, [ready, user, role, router]);
  return user && token && user.role === role ? { user, token } : null;
}
