import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "interview-agent:username";

interface UserContextValue {
  username: string | null;
  displayName: string | null;
  isInitialized: boolean;
  setUsername: (name: string) => void;
  clearUsername: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

function normalize(name: string): string {
  return name.trim();
}

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [username, setUsernameState] = useState<string | null>(null);
  const [isInitialized, setInitialized] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        setUsernameState(raw);
      }
    } catch {
      // localStorage может быть недоступен в SSR / при блокировке — игнорируем
    }
    setInitialized(true);
  }, []);

  const setUsername = useCallback((name: string) => {
    const normalized = normalize(name);
    if (!normalized) return;
    setUsernameState(normalized);
    try {
      localStorage.setItem(STORAGE_KEY, normalized);
    } catch {
      // ignore
    }
  }, []);

  const clearUsername = useCallback(() => {
    setUsernameState(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<UserContextValue>(
    () => ({
      username,
      displayName: username,
      isInitialized,
      setUsername,
      clearUsername,
    }),
    [username, isInitialized, setUsername, clearUsername],
  );

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
};

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) {
    throw new Error("useUser must be used inside UserProvider");
  }
  return ctx;
}
