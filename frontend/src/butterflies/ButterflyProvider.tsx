import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Butterfly, type ButterflyPalette } from "./Butterfly";

/**
 * Success-only butterfly celebrations.
 *
 *   login      – a small flock flies across the screen after signing in
 *   ask        – a small flock flies across when a question goes to Sir's Office
 *   workflow   – two or three rise near the completed results panel
 *   save       – a brief butterfly confirms a saved fundraiser
 *   reflection – one rises beside a saved historical event or reflection
 *   milestone  – a small, subtle flutter for recorded milestones
 *
 * Nothing plays when the user turned animations off in Settings or the device
 * prefers reduced motion. The layer never takes pointer events and is hidden
 * from screen readers.
 */
export type CelebrationKind = "login" | "ask" | "workflow" | "save" | "reflection" | "milestone";

type Flight = {
  id: number;
  path: string;
  duration: number;
  delay: number;
  size: number;
  palette: ButterflyPalette;
  flap: number;
};

type Ctx = {
  celebrate: (kind: CelebrationKind, anchor?: Element | null, allowedOverride?: boolean) => void;
  active: boolean;
  reducedMotion: boolean;
};

const ButterflyContext = createContext<Ctx>({ celebrate: () => {}, active: false, reducedMotion: false });

const MAX_FLIGHTS = 10;
const jitter = (value: number, spread: number) => value + (Math.random() * 2 - 1) * spread;

export function usePrefersReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function rise(x: number, y: number, height: number, sway: number): string {
  return `M ${x} ${y} C ${x - sway} ${y - height * 0.3}, ${x + sway * 1.4} ${y - height * 0.6}, ${x + sway * 0.4} ${y - height}`;
}

/** A flock crossing the whole screen on gentle S-curves, mostly left to right, staggered so it reads as a flight, not a burst. */
function flock(count: number, nextId: () => number): Flight[] {
  const w = window.innerWidth;
  const h = window.innerHeight;
  return Array.from({ length: count }, (_, i) => {
    const rtl = i % 4 === 3;
    const [x0, x1] = rtl ? [w + 70, -70] : [-70, w + 70];
    const y0 = h * (0.15 + Math.random() * 0.7);
    const y1 = h * (0.1 + Math.random() * 0.75);
    const c1 = h * (0.05 + Math.random() * 0.9);
    const c2 = h * (0.05 + Math.random() * 0.9);
    return {
      id: nextId(),
      path: `M ${x0} ${y0} C ${x0 + (x1 - x0) * 0.33} ${c1}, ${x0 + (x1 - x0) * 0.66} ${c2}, ${x1} ${y1}`,
      duration: jitter(5200, 700), delay: i * 220 + Math.random() * 120, size: Math.round(jitter(36, 10)),
      palette: (i % 3) as ButterflyPalette, flap: jitter(0.3, 0.05),
    };
  });
}

function buildFlights(kind: CelebrationKind, anchor: DOMRect | null, nextId: () => number): Flight[] {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const box = anchor ?? new DOMRect(w * 0.35, h * 0.55, w * 0.3, h * 0.2);
  const palette = () => Math.floor(Math.random() * 3) as ButterflyPalette;

  switch (kind) {
    case "login":
      return flock(8, nextId);
    case "ask":
      return flock(6, nextId);
    case "workflow":
      return [0.28, 0.52, 0.76].map((fx, i) => ({
        id: nextId(),
        path: rise(box.left + box.width * fx, box.top + Math.min(box.height, 160) * 0.6, jitter(230, 30), jitter(28, 10)),
        duration: jitter(3000, 250), delay: i * 230, size: [34, 42, 30][i], palette: palette(), flap: jitter(0.32, 0.05),
      }));
    case "save":
      return [{
        id: nextId(),
        path: rise(box.left + box.width * 0.5, box.top + box.height * 0.5, 170, 26),
        duration: 2300, delay: 0, size: 34, palette: palette(), flap: 0.3,
      }];
    case "reflection":
      return [{
        id: nextId(),
        path: rise(box.right + 18, box.top + box.height * 0.5, 190, -24),
        duration: 2700, delay: 60, size: 34, palette: palette(), flap: 0.33,
      }];
    case "milestone":
      return [0.15, 0.4, 0.65, 0.88].map((fx, i) => ({
        id: nextId(),
        path: rise(box.left + box.width * fx, box.top + box.height * 0.5, jitter(150, 30), jitter(20, 12)),
        duration: jitter(3200, 300), delay: i * 160, size: jitter(22, 4), palette: palette(), flap: jitter(0.3, 0.05),
      }));
  }
}

export function ButterflyProvider({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const reducedMotion = usePrefersReducedMotion();
  const active = enabled && !reducedMotion;
  const [flights, setFlights] = useState<Flight[]>([]);
  const counter = useRef(0);
  const state = useRef({ active, reducedMotion });
  state.current = { active, reducedMotion };

  const celebrate = useCallback((kind: CelebrationKind, anchor?: Element | null, allowedOverride?: boolean) => {
    const { active: isActive, reducedMotion: isReduced } = state.current;
    const allowed = allowedOverride === undefined ? isActive : allowedOverride && !isReduced;
    if (!allowed) return;
    const rect = anchor ? anchor.getBoundingClientRect() : null;
    const made = buildFlights(kind, rect, () => ++counter.current);
    setFlights((current) => [...current, ...made].slice(-MAX_FLIGHTS));
  }, []);

  const remove = useCallback((id: number) => setFlights((current) => current.filter((f) => f.id !== id)), []);
  const value = useMemo(() => ({ celebrate, active, reducedMotion }), [celebrate, active, reducedMotion]);

  return (
    <ButterflyContext.Provider value={value}>
      {children}
      <div className="butterfly-layer" aria-hidden="true" data-testid="butterfly-layer">
        {flights.map((f) => (
          <div
            key={f.id}
            className="butterfly-flight"
            data-butterfly="flight"
            style={{ offsetPath: `path("${f.path}")`, animationDuration: `${f.duration}ms`, animationDelay: `${f.delay}ms` }}
            onAnimationEnd={(e) => e.target === e.currentTarget && remove(f.id)}
          >
            <div className="butterfly-sway">
              <Butterfly size={f.size} palette={f.palette} flap={f.flap} />
            </div>
          </div>
        ))}
      </div>
    </ButterflyContext.Provider>
  );
}

export const useButterflies = () => useContext(ButterflyContext);
