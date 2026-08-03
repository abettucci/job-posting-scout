"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const u = await api.me();
      setUser(u);
    } catch {
      setUser(null);
    }
  };

  useEffect(() => {
    const jwt = localStorage.getItem("jwt");
    if (!jwt) {
      setLoading(false);
      return;
    }
    refresh().finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const { token, user: u } = await api.login(email, password);
    localStorage.setItem("jwt", token);
    setUser(u);
  };

  const signup = async (email: string, password: string) => {
    const { token, user: u } = await api.signup(email, password);
    localStorage.setItem("jwt", token);
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem("jwt");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
