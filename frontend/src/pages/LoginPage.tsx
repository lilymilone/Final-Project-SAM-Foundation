import { ArrowRight, Eye, EyeOff, GraduationCap, Lock, Mail } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Butterfly } from "../butterflies/Butterfly";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { Logo, Wordmark } from "../components/Brand";

/** Documented default for the synthetic demo accounts (README + seed). Not a real credential. */
const DEMO_PASSWORD = "SmileLikeSab-demo";

type DemoAccounts = {
  demo_mode: boolean;
  accounts: { email: string; first_name: string; role: string; title: string }[];
  default_password: boolean;
};

export default function LoginPage() {
  const { user, login, sessionExpired } = useAuth();
  const { celebrate } = useButterflies();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [demo, setDemo] = useState<DemoAccounts | null>(null);

  useEffect(() => {
    api<DemoAccounts>("/api/auth/demo-accounts").then(setDemo).catch(() => setDemo(null));
  }, []);

  if (user) return <Navigate to="/" replace />;
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const signedIn = await login(email, password);
      navigate(from, { replace: true });
      celebrate("login", null, signedIn.settings.animations_enabled);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <section className="sidebar-surface relative hidden overflow-hidden lg:flex lg:flex-col lg:items-center lg:justify-center lg:px-12">
        <Butterfly size={54} motion="still" palette={0} className="absolute left-[12%] top-[14%] rotate-[-14deg] opacity-70" />
        <Butterfly size={34} motion="still" palette={2} className="absolute right-[16%] top-[22%] rotate-[18deg] opacity-60" />
        <Butterfly size={42} motion="still" palette={1} className="absolute bottom-[5%] right-[7%] rotate-[-8deg] opacity-50" />
        <Logo size={300} className="!rounded-[2rem] !p-5" />
        <div className="mt-10 text-center">
          <div className="flex justify-center">
            <Wordmark size="lg" />
          </div>
          <p className="mx-auto mt-6 max-w-md font-display text-xl italic leading-relaxed text-lilac/90">
            Created in loving memory of Sabrina Audrey Milone. Supporting mental health awareness, eating disorder
            research, and the communities that hold us up.
          </p>
        </div>
      </section>

      {/* Sign-in panel */}
      <section className="app-backdrop flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center gap-4 lg:hidden">
            <Logo size={150} />
            <Wordmark tone="dark" />
          </div>

          <div className="card p-7 sm:p-9">
            <p className="eyebrow">Board sign-in</p>
            <h1 className="mt-2 font-display text-[2.3rem] font-semibold leading-tight text-plum">Welcome back</h1>
            <p className="mt-1 text-sm text-muted">Sign in to plan, learn, and decide together.</p>

            {sessionExpired && (
              <p role="status" className="mt-5 rounded-xl bg-lilac px-4 py-3 text-sm text-plum">
                Your session expired. Please sign in again.
              </p>
            )}

            <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
              <div>
                <label htmlFor="email" className="label">Email</label>
                <div className="relative">
                  <Mail size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-lavender" aria-hidden="true" />
                  <input id="email" type="email" autoComplete="username" className="field !pl-10" value={email}
                    onChange={(e) => setEmail(e.target.value)} placeholder="you@foundation.org" required />
                </div>
              </div>
              <div>
                <label htmlFor="password" className="label">Password</label>
                <div className="relative">
                  <Lock size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-lavender" aria-hidden="true" />
                  <input id="password" type={showPassword ? "text" : "password"} autoComplete="current-password"
                    className="field !pl-10 !pr-11" value={password} onChange={(e) => setPassword(e.target.value)} required />
                  <button type="button" onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-muted hover:text-plum"
                    aria-label={showPassword ? "Hide password" : "Show password"}>
                    {showPassword ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                  </button>
                </div>
              </div>
              {error && (
                <p role="alert" className="rounded-xl bg-[#fbeef3] px-4 py-3 text-sm text-danger">{error}</p>
              )}
              <button type="submit" className="btn btn-primary w-full !py-3" disabled={submitting || !email || !password}>
                {submitting ? "Signing in…" : <>Sign in <ArrowRight size={16} aria-hidden="true" /></>}
              </button>
            </form>
          </div>

          {demo?.demo_mode && demo.accounts.length > 0 && (
            <div className="mt-5 rounded-2xl border border-rose/30 bg-blush/45 p-5">
              <p className="flex items-center gap-2 text-sm font-semibold text-plum">
                <GraduationCap size={17} aria-hidden="true" /> Teaching staff demo
              </p>
              <p className="mt-1 text-xs text-muted">
                Synthetic accounts and data only.
                {demo.default_password ? <> Password for both: <code className="rounded bg-white/70 px-1.5 py-0.5 text-plum">{DEMO_PASSWORD}</code></> : " The password was changed via DEMO_PASSWORD."}
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {demo.accounts.map((a) => (
                  <button key={a.email} type="button" className="rounded-xl border border-white/80 bg-white/80 px-3.5 py-2.5 text-left transition hover:border-lavender hover:bg-white"
                    onClick={() => { setEmail(a.email); if (demo.default_password) setPassword(DEMO_PASSWORD); }}>
                    <span className="block text-sm font-semibold text-plum">{a.title}</span>
                    <span className="block text-xs text-muted">{a.email}</span>
                    <span className="mt-1 block text-[0.7rem] text-royal">{a.role === "chair" ? "Full access" : "No donor or financial access"}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
