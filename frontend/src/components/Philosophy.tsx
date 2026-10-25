import { Butterfly } from "../butterflies/Butterfly";

export const PHILOSOPHY = "Be somebody who makes everybody feel like somebody.";

/** The foundation's guiding philosophy, shown on the Overview beneath the welcome. */
export function PhilosophyQuote() {
  return (
    <figure className="philosophy relative mb-6 overflow-hidden rounded-3xl px-6 py-7 text-center sm:px-12 animate-fade-up"
      aria-label="Our guiding philosophy">
      <Butterfly size={30} motion="still" palette={0} className="absolute left-5 top-4 -rotate-12 opacity-70" />
      <Butterfly size={22} motion="still" palette={2} className="absolute bottom-4 right-7 rotate-12 opacity-60" />
      <blockquote>
        <p className="font-display text-[1.65rem] font-medium italic leading-snug text-royal sm:text-[2.05rem]">
          <span aria-hidden="true" className="mr-1 text-lavender">“</span>{PHILOSOPHY}<span aria-hidden="true" className="ml-1 text-lavender">”</span>
        </p>
      </blockquote>
      <figcaption className="mt-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted">
        Our guiding philosophy · in memory of Sabrina
      </figcaption>
    </figure>
  );
}
