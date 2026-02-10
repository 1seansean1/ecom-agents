import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/lib/auth';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from ?? '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex items-center justify-center h-full bg-[var(--color-bg)]">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm p-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]"
      >
        <div className="mb-6 text-center">
          <h1 className="text-lg font-semibold text-[var(--color-text)]">Holly Grace</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">Sign in to continue</p>
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 text-xs rounded bg-[var(--color-error)]/10 text-[var(--color-error)] border border-[var(--color-error)]/20">
            {error}
          </div>
        )}

        <label className="block mb-4">
          <span className="text-xs text-[var(--color-text-muted)]">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            className="mt-1 block w-full px-3 py-2 text-sm rounded border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none"
            placeholder="you@example.com"
          />
        </label>

        <label className="block mb-6">
          <span className="text-xs text-[var(--color-text-muted)]">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 block w-full px-3 py-2 text-sm rounded border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none"
          />
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full py-2 text-sm font-medium rounded bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
