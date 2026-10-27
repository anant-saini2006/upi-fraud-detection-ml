'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import {
  api,
  clearAdminToken,
  clearAuthToken,
  getAuthToken,
  setAdminToken,
  setAuthToken,
  type AuthUser,
} from '@/lib/api';

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  login: (credentials: { email: string; password: string }) => Promise<AuthUser>;
  signup: (details: { full_name: string; email: string; password: string }) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const USER_CACHE_KEY = 'auth_user_cache';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Load initial session on mount
  useEffect(() => {
    const savedToken = getAuthToken();
    if (!savedToken) {
      setIsLoading(false);
      return;
    }

    setTokenState(savedToken);

    // Optimistically load cached user profile to prevent layout shift
    try {
      const cached = localStorage.getItem(USER_CACHE_KEY);
      if (cached) {
        setUser(JSON.parse(cached));
      }
    } catch {
      // Ignore cache parse error
    }

    // Verify token with backend
    api
      .authMe()
      .then((verifiedUser) => {
        setUser(verifiedUser);
        localStorage.setItem(USER_CACHE_KEY, JSON.stringify(verifiedUser));
        if (verifiedUser.role === 'admin') {
          setAdminToken(savedToken);
        }
      })
      .catch(() => {
        // Token invalid or expired
        setUser(null);
        clearAuthToken();
        clearAdminToken();
        setTokenState(null);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  const login = async (credentials: { email: string; password: string }): Promise<AuthUser> => {
    setIsLoading(true);
    try {
      const res = await api.authLogin(credentials);
      setAuthToken(res.token);
      setTokenState(res.token);
      setUser(res.user);
      localStorage.setItem(USER_CACHE_KEY, JSON.stringify(res.user));

      if (res.user.role === 'admin') {
        setAdminToken(res.token);
      }
      return res.user;
    } finally {
      setIsLoading(false);
    }
  };

  const signup = async (details: {
    full_name: string;
    email: string;
    password: string;
  }): Promise<AuthUser> => {
    setIsLoading(true);
    try {
      const res = await api.authSignup(details);
      setAuthToken(res.token);
      setTokenState(res.token);
      setUser(res.user);
      localStorage.setItem(USER_CACHE_KEY, JSON.stringify(res.user));
      return res.user;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      await api.authLogout().catch(() => {});
    } finally {
      clearAuthToken();
      clearAdminToken();
      setUser(null);
      setTokenState(null);
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }
  };

  const refreshUser = async () => {
    const t = getAuthToken();
    if (!t) {
      setUser(null);
      return;
    }
    try {
      const u = await api.authMe();
      setUser(u);
      localStorage.setItem(USER_CACHE_KEY, JSON.stringify(u));
    } catch {
      setUser(null);
      clearAuthToken();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        login,
        signup,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
