"use client";

import { gsap, SplitText } from "../motion";

const GLYPHS = "ABCDEFGHKLMNPRSTUVWXYZ0123456789/·.-";

/**
 * Decode `el` from noise into its final text. Writes textContent only (no
 * layout change: every scrambled node is mono with a fixed `ch` width).
 * Returns a tween so callers can sequence it on a timeline.
 */
export function scramble(el: HTMLElement, opts: { duration?: number; delay?: number; settle?: number } = {}) {
  const final = el.dataset.text ?? el.textContent ?? "";
  el.dataset.text = final;
  const state = { p: 0 };
  const settle = opts.settle ?? 0.55; // fraction of the tween spent locking chars left→right
  return gsap.to(state, {
    p: 1,
    duration: opts.duration ?? 1.1,
    delay: opts.delay ?? 0,
    ease: "none",
    onUpdate() {
      const locked = Math.floor(Math.max(0, (state.p - (1 - settle)) / settle) * final.length);
      let out = "";
      for (let i = 0; i < final.length; i++) {
        const ch = final[i];
        out += i < locked || ch === " " ? ch : GLYPHS[(Math.random() * GLYPHS.length) | 0];
      }
      el.textContent = out;
    },
    onComplete() {
      el.textContent = final;
    },
  });
}

/** Fill an element with noise of the same length as its final text. */
export function noiseOut(el: HTMLElement) {
  const final = el.dataset.text ?? el.textContent ?? "";
  el.dataset.text = final;
  el.textContent = final.replace(/[^ ]/g, () => GLYPHS[(Math.random() * GLYPHS.length) | 0]);
}

/**
 * Position of `el` inside `ancestor`, from offsetLeft/offsetTop -- which,
 * unlike getBoundingClientRect, ignore transforms. So it can be read in the
 * middle of a scrubbed timeline without picking up the timeline's own state.
 */
export function offsetWithin(el: HTMLElement, ancestor: HTMLElement) {
  let x = 0;
  let y = 0;
  let n: HTMLElement | null = el;
  while (n && n !== ancestor) {
    x += n.offsetLeft;
    y += n.offsetTop;
    n = n.offsetParent as HTMLElement | null;
  }
  return { x, y, w: el.offsetWidth, h: el.offsetHeight };
}

/**
 * Masked line reveal for every [data-split] heading in `scope`. autoSplit
 * re-splits after webfonts load or the width changes, and returning the
 * tween from onSplit lets SplitText tear the old one down cleanly.
 */
export function revealSplits(scope: Element) {
  scope.querySelectorAll<HTMLElement>("[data-split]").forEach((el) => {
    SplitText.create(el, {
      type: "lines",
      mask: "lines",
      linesClass: "nb-line",
      autoSplit: true,
      onSplit: (self) =>
        gsap.from(self.lines, {
          yPercent: 112,
          duration: 1.15,
          stagger: 0.09,
          ease: "expo.out",
          scrollTrigger: { trigger: el, start: "top 88%", toggleActions: "play none none reverse" },
        }),
    });
  });
}
