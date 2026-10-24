import { useId } from "react";

/** Watercolor palettes drawn from the Smile Like Sab logo. */
const PALETTES = [
  { fore: ["#B69AD9", "#F3C6DD"], hind: ["#70409B", "#D58AB8"] },
  { fore: ["#8B5CC0", "#E3B5D6"], hind: ["#5A2D85", "#B69AD9"] },
  { fore: ["#E7A6CB", "#C9B2EA"], hind: ["#9E6CC6", "#F6D6E8"] },
] as const;

export type ButterflyPalette = 0 | 1 | 2;

type Props = {
  size?: number;
  palette?: ButterflyPalette;
  /** Seconds per wing beat (half cycle). */
  flap?: number;
  /** "still" draws a static mark (no wing motion), for headings and empty states. */
  motion?: "flap" | "still";
  className?: string;
};

function Wing({ id }: { id: string }) {
  return (
    <>
      {/* forewing */}
      <path
        d="M49 38 C40 22 22 6 9 10 C-1 13 2 30 12 38 C22 45 38 44 49 41 Z"
        fill={`url(#${id}-fore)`}
      />
      <path d="M46 37 C36 28 22 17 12 17" stroke="#fff" strokeOpacity="0.45" strokeWidth="0.9" fill="none" />
      <ellipse cx="22" cy="24" rx="7" ry="4.5" fill="#fff" opacity="0.28" transform="rotate(-28 22 24)" />
      {/* hindwing */}
      <path
        d="M49 44 C38 46 22 52 18 64 C15 75 26 83 35 76 C43 69 47 56 49 47 Z"
        fill={`url(#${id}-hind)`}
      />
      <circle cx="29" cy="66" r="3.2" fill="#fff" opacity="0.3" />
    </>
  );
}

/** An elegant SVG butterfly. Decorative: always aria-hidden. */
export function Butterfly({ size = 36, palette = 0, flap = 0.34, motion = "flap", className = "" }: Props) {
  const id = useId().replace(/:/g, "");
  const colors = PALETTES[palette];
  return (
    <svg
      width={size}
      height={size * 0.9}
      viewBox="0 0 100 90"
      aria-hidden="true"
      focusable="false"
      className={`${motion === "still" ? "butterfly-still" : ""} ${className}`}
      style={{ ["--flap" as string]: `${flap}s`, overflow: "visible" }}
    >
      <defs>
        <linearGradient id={`${id}-fore`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={colors.fore[0]} />
          <stop offset="1" stopColor={colors.fore[1]} stopOpacity="0.92" />
        </linearGradient>
        <linearGradient id={`${id}-hind`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor={colors.hind[0]} />
          <stop offset="1" stopColor={colors.hind[1]} stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <g className={motion === "flap" ? "butterfly-wing-left" : undefined}>
        <Wing id={id} />
      </g>
      <g className={motion === "flap" ? "butterfly-wing-right" : undefined}>
        <g transform="translate(100 0) scale(-1 1)">
          <Wing id={id} />
        </g>
      </g>
      {/* body, head, antennae */}
      <ellipse cx="50" cy="47" rx="2.3" ry="15" fill="#32124F" />
      <circle cx="50" cy="30" r="2.7" fill="#32124F" />
      <path d="M49 28 C47 19 43 14 38 11 M51 28 C53 19 57 14 62 11" stroke="#32124F" strokeWidth="1.1" strokeLinecap="round" fill="none" />
      <circle cx="38" cy="11" r="1.3" fill="#32124F" />
      <circle cx="62" cy="11" r="1.3" fill="#32124F" />
    </svg>
  );
}
