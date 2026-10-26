import { BrainCircuit, Sparkles, UserRound } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import type { Strategy, UserSettings } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { Card, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

export default function SettingsPage() {
  const { user, updateUser } = useAuth();
  const { celebrate, reducedMotion } = useButterflies();
  const { data, error, loading, reload, setData } = useApi<UserSettings>("/api/settings");
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [saving, setSaving] = useState(false);
  const previewRef = useRef<HTMLButtonElement>(null);
  const clearToast = useCallback(() => setToast(null), []);

  async function save(patch: Partial<Pick<UserSettings, "animations_enabled" | "model_strategy">>) {
    setSaving(true);
    try {
      const next = await api<UserSettings>("/api/settings", { method: "PUT", json: patch });
      setData(next);
      updateUser({ settings: { animations_enabled: next.animations_enabled, model_strategy: next.model_strategy } });
      setToast({ message: "Settings saved", tone: "success" });
    } catch (err) {
      setToast({ message: err instanceof Error ? err.message : "Could not save", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Settings" title="Make SAM SPACE yours" subtitle="Your preferences are saved to your account on the server." />
      {loading && <LoadingState rows={3} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && user && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Card title="Profile" icon={<UserRound size={16} aria-hidden="true" />}>
            <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-y-2 text-sm">
              <dt className="text-muted">Name</dt><dd className="font-semibold text-plum">{user.first_name} {user.last_name}</dd>
              <dt className="text-muted">Email</dt><dd>{user.email}</dd>
              <dt className="text-muted">Board role</dt><dd>{user.title}</dd>
              <dt className="text-muted">Access</dt><dd className="text-xs text-muted">{user.permissions.map((p) => p.replace(/_/g, " ")).join(" · ")}</dd>
            </dl>
          </Card>

          <Card title="Animations" icon={<Sparkles size={16} aria-hidden="true" />}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p id="anim-label" className="font-semibold text-plum">Celebration butterflies</p>
                <p className="mt-0.5 text-sm text-muted">A few butterflies appear only when something succeeds: signing in, saving, finishing a workflow.</p>
              </div>
              <button
                role="switch"
                aria-checked={data.animations_enabled}
                aria-labelledby="anim-label"
                disabled={saving}
                onClick={() => save({ animations_enabled: !data.animations_enabled })}
                className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${data.animations_enabled ? "bg-royal" : "bg-lavender/50"}`}
              >
                <span className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all ${data.animations_enabled ? "left-6" : "left-1"}`} />
              </button>
            </div>
            {reducedMotion && (
              <p className="mt-3 rounded-xl bg-lilac/60 px-3 py-2 text-xs text-plum">
                Your device asks for reduced motion, so butterflies stay hidden whatever this switch says.
              </p>
            )}
            <button ref={previewRef} className="btn btn-soft mt-4 text-sm" onClick={() => celebrate("save", previewRef.current)}
              disabled={!data.animations_enabled || reducedMotion}>
              Preview a butterfly
            </button>
          </Card>

          <Card title="AI Model Strategy" icon={<BrainCircuit size={16} aria-hidden="true" />} className="lg:col-span-2">
            {data.strategy_note && (
              <p className="mb-3 rounded-xl bg-plum px-3.5 py-2.5 text-sm text-white">{data.strategy_note}</p>
            )}
            <fieldset>
              <legend className="sr-only">AI Model Strategy</legend>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {data.strategies.map((s) => {
                  const checked = data.model_strategy === s.value;
                  return (
                    <label key={s.value}
                      className={`cursor-pointer rounded-2xl border p-4 transition ${checked ? "border-royal bg-lilac/70 shadow-sm" : "border-lavender/40 bg-white/70 hover:border-lavender"}`}>
                      <input type="radio" name="strategy" value={s.value} checked={checked} disabled={saving}
                        onChange={() => save({ model_strategy: s.value as Strategy })} className="sr-only" />
                      <span className="flex items-center justify-between">
                        <span className="font-display text-xl font-semibold text-plum">{s.label}</span>
                        {s.value === "auto" && <span className="rounded-full bg-white px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-royal">Default</span>}
                      </span>
                      <span className="mt-1 block text-sm text-muted">{s.description}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <p className="mt-3 text-xs text-muted">See exactly which model each task gets in Analytics & Safety. Budget limits apply under every strategy.</p>
          </Card>
        </div>
      )}
      {toast && <Toast message={toast.message} tone={toast.tone} onDone={clearToast} />}
    </>
  );
}
