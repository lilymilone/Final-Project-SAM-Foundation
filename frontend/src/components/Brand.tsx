import { useState } from "react";
import { Butterfly } from "../butterflies/Butterfly";

export const LOGO_SRC = "/brand/smile-like-sab.png";

/**
 * The authentic Smile Like Sab logo, shown exactly as provided: no crop,
 * filter, or recolor, with its aspect ratio preserved. It sits on a white card
 * because the artwork has a white background. If the file is missing, a
 * quiet text fallback keeps the layout intact.
 */
export function Logo({ className = "", size = 160 }: { className?: string; size?: number }) {
  const [missing, setMissing] = useState(false);
  return (
    <div
      className={`inline-flex items-center justify-center rounded-[1.4rem] bg-white p-3 shadow-[var(--shadow-soft)] ring-1 ring-lavender/40 ${className}`}
      style={{ width: size, height: size }}
    >
      {missing ? (
        <div className="flex flex-col items-center gap-1 text-center" role="img" aria-label="Smile Like Sab">
          <Butterfly size={size * (size >= 120 ? 0.4 : 0.62)} motion="still" />
          {size >= 120 && <span className="font-display text-xl italic text-royal">Smile Like Sab</span>}
        </div>
      ) : (
        <img
          src={LOGO_SRC}
          alt="Smile Like Sab logo"
          className="h-full w-full object-contain"
          draggable={false}
          onError={() => {
            console.warn("Logo not found at assets/smile-like-sab.png");
            setMissing(true);
          }}
        />
      )}
    </div>
  );
}

/** SAM SPACE wordmark: spaced serif capitals with a small butterfly ligature. */
export function Wordmark({ tone = "light", size = "md" }: { tone?: "light" | "dark"; size?: "md" | "lg" }) {
  const color = tone === "light" ? "text-white" : "text-plum";
  const text = size === "lg" ? "text-4xl sm:text-5xl" : "text-[1.35rem]";
  return (
    <div className="flex flex-col items-start leading-none">
      <span className={`wordmark ${text} ${color} inline-flex items-center gap-[0.35em]`} aria-label="SAM SPACE">
        <span aria-hidden="true">SAM</span>
        <Butterfly size={size === "lg" ? 34 : 18} motion="still" palette={tone === "light" ? 0 : 1} />
        <span aria-hidden="true">SPACE</span>
      </span>
      <span
        className={`mt-1.5 font-display italic ${size === "lg" ? "text-lg" : "text-[0.82rem]"} ${
          tone === "light" ? "text-lilac/80" : "text-muted"
        }`}
      >
        a board studio for Smile Like Sab
      </span>
    </div>
  );
}
