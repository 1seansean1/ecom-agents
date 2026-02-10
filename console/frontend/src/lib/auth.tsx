/**
 * Auth context — cookie-based authentication.
 * The JWT lives in an httpOnly cookie; JS never touches it.
 * We track login state via a /api/auth/me probe.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface AuthState {
  email: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, probe /api/auth/me to check if cookie is still valid
  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setEmail(data?.email ?? null))
      .catch(() => setEmail(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(em: string, pw: string) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email: em, password: pw }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? 'Login failed');
    }
    const data = await res.json();
    setEmail(data.email);
  }

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {});
    setEmail(null);
  }

  return (
    <AuthContext.Provider value={{ email, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Wrap protected routes — redirects to /login if not authenticated. */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { email, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!loading && !email) {
      navigate('/login', { replace: true, state: { from: location.pathname } });
    }
  }, [loading, email, navigate, location.pathname]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-[var(--color-bg)]">
        <div className="w-6 h-6 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return email ? <>{children}</> : null;
}
