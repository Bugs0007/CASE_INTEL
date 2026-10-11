"use client";

/**
 * Shared motion plumbing for the landing page.
 *
 * Every animated thing on the page is built inside
 * `gsap.matchMedia().add(MOTION, ...)`, so when the OS asks for reduced
 * motion nothing is ever created: the markup's static end state IS the
 * fallback, with no pins, no smooth scroll and no WebGL.
 */

import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";
import type Lenis from "lenis";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP);
  // Mobile URL-bar show/hide fires resize; refreshing pins on it is the
  // classic source of jumpy pinned sections on phones.
  ScrollTrigger.config({ ignoreMobileResize: true });
}

export { gsap, ScrollTrigger, SplitText, useGSAP };

export const MOTION = "(prefers-reduced-motion: no-preference)";
export const DESKTOP = "(min-width: 768px)";
export const FINE = "(pointer: fine)";

/* ------------------------------------------------------------------ lenis */

let lenis: Lenis | null = null;
export const setLenis = (l: Lenis | null) => {
  lenis = l;
};
export const getLenis = () => lenis;

/** Scroll to an element or offset, through Lenis when it's running. */
export function scrollToTarget(target: string | HTMLElement | number, opts: { duration?: number; offset?: number } = {}) {
  if (lenis) {
    lenis.scrollTo(target, { duration: opts.duration ?? 1.4, offset: opts.offset ?? 0, force: true });
    return;
  }
  const el = typeof target === "string" ? document.querySelector<HTMLElement>(target) : target;
  const top =
    typeof el === "number" ? el : el ? el.getBoundingClientRect().top + window.scrollY + (opts.offset ?? 0) : 0;
  window.scrollTo({ top, behavior: matchMedia(MOTION).matches ? "smooth" : "auto" });
}

/* ---------------------------------------------------------------- the clock */

/**
 * The fixed corner clock is driven by scroll, not by React state: each scene
 * registers a [from, to] time range against its own ScrollTrigger and writes
 * straight into the DOM node, so scrolling never re-renders the tree.
 */
let clockEl: HTMLElement | null = null;
let clockMeta: HTMLElement | null = null;
export const bindClock = (el: HTMLElement | null, meta: HTMLElement | null) => {
  clockEl = el;
  clockMeta = meta;
};

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};
const fmt = (mins: number) => {
  const m = ((Math.round(mins) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

export function setClock(text: string, meta?: string) {
  if (clockEl && clockEl.textContent !== text) clockEl.textContent = text;
  if (meta !== undefined && clockMeta && clockMeta.textContent !== meta) clockMeta.textContent = meta;
}

/** Interpolate the clock across a scroll progress, wrapping past midnight. */
export function clockAt(from: string, to: string, p: number) {
  const a = toMin(from);
  let b = toMin(to);
  if (b < a) b += 1440;
  return fmt(a + (b - a) * Math.min(1, Math.max(0, p)));
}

/** Register a ScrollTrigger that advances the clock across `trigger`. */
export function clockRange(trigger: Element, from: string, to: string, meta: string, start = "top 60%", end = "bottom 40%") {
  return ScrollTrigger.create({
    trigger,
    start,
    end,
    onUpdate: (st) => setClock(clockAt(from, to, st.progress), meta),
    onEnter: () => setClock(from, meta),
    onEnterBack: () => setClock(to, meta),
  });
}
