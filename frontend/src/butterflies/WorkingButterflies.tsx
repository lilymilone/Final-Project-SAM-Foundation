import { createPortal } from "react-dom";
import { Butterfly, type ButterflyPalette } from "./Butterfly";
import { useButterflies } from "./ButterflyProvider";

const FLYERS: { side: "left" | "right"; size: number; palette: ButterflyPalette; delay: number; duration: number; drift: number; inset: number }[] = [
  { side: "left", size: 36, palette: 0, delay: 0, duration: 9, drift: 26, inset: 10 },
  { side: "left", size: 26, palette: 2, delay: 3.2, duration: 11, drift: -18, inset: 34 },
  { side: "left", size: 30, palette: 1, delay: 6.1, duration: 10, drift: 22, inset: 6 },
  { side: "right", size: 32, palette: 2, delay: 1.4, duration: 10, drift: -24, inset: 12 },
  { side: "right", size: 38, palette: 0, delay: 4.6, duration: 12, drift: 18, inset: 36 },
  { side: "right", size: 24, palette: 1, delay: 7.4, duration: 9, drift: -16, inset: 8 },
];

/** While the agents work, a few butterflies drift up both edges of the screen. Decorative only: hidden from screen readers,
 *  never blocks clicks, and off when the board member turns animations off or the system asks for reduced motion. */
export function WorkingButterflies() {
  const { active } = useButterflies();
  if (!active) return null;
  return createPortal(
    <div className="working-butterflies" aria-hidden="true" data-testid="working-butterflies">
      {FLYERS.map((f, i) => (
        <div key={i} className={`working-butterfly working-${f.side}`}
          style={{ ["--inset" as string]: `${f.inset}px`, ["--drift" as string]: `${f.drift}px`, animationDelay: `${f.delay}s`, animationDuration: `${f.duration}s` }}>
          <div className="butterfly-sway"><Butterfly size={f.size} palette={f.palette} flap={0.3 + (i % 3) * 0.05} /></div>
        </div>
      ))}
    </div>,
    document.body,
  );
}
