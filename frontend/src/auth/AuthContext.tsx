import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, onUnauthorized } from "../api/client";
import type { User } from "../api/types";

type AuthState = {
  user: User | null;
  loading: boolean;
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  updateUser: (patch: Partial<User>) => void;
  can: (permission: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    api<{ user: User | null }>("/api/auth/session")
      .then((r) => setUser(r.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(
    () =>
      onUnauthorized(() => {
        setUser((current) => {
          if (current) setSessionExpired(true);
          return null;
        });
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ user: User }>("/api/auth/login", { json: { email, password } });
    setSessionExpired(false);
    setUser(r.user);
    return r.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }, []);

  const updateUser = useCallback((patch: Partial<User>) => setUser((u) => (u ? { ...u, ...patch } : u)), []);
  const can = useCallback((permission: string) => !!user?.permissions.includes(permission), [user]);

  const value = useMemo(
    () => ({ user, loading, sessionExpired, login, logout, updateUser, can }),
    [user, loading, sessionExpired, login, logout, updateUser, can],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
