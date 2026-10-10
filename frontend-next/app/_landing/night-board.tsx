"use client";

/**
 * "Night Board" -- the landing page as one night in an advocate's practice,
 * 19:02 (the cause list is fetched) to 10:30 (court). See app/_landing/data.ts
 * for the sample data and the scene files for the claims, each of which
 * traces to CLAUDE.md.
 */

import Link from "next/link";
import Lenis from "lenis";
import { useEffect, useRef, useState } from "react";
import { gsap, ScrollTrigger, useGSAP, MOTION, FINE, DESKTOP, bindClock, clockAt, setClock, setLenis, scrollToTarget } from "./motion";
import { Hero, Flight } from "./scenes/hero";
import { FanOut } from "./scenes/fanout";
import { OrderToTasks } from "./scenes/order";
import { XRay } from "./scenes/xray";
import { CaseBot } from "./scenes/casebot";
import { Toolkit } from "./scenes/toolkit";
import { Trust } from "./scenes/trust";
import { Finale } from "./scenes/finale";
import { CommandPalette } from "./ui/palette";
import { AuthLink } from "./ui/bits";

const EGG = "objection";

export default function NightBoard() {
  const root = useRef<HTMLDivElement>(null);
  const [palette, setPalette] = useState(false);
  const [isMac, setIsMac] = useState(true);

  useEffect(() => {
    setIsMac(/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent));
  }, []);

  /* ---- keyboard: Cmd/Ctrl+K, and the easter egg ---- */
  useEffect(() => {
    let buf = "";
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openPalette();
        return;
      }
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.length !== 1) return;
      buf = (buf + e.key.toLowerCase()).slice(-EGG.length);
      if (buf === EGG) {
        buf = "";
        overruled();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openPalette = () => {
    const vt = (document as Document & { startViewTransition?: (cb: () => void) => unknown }).startViewTransition;
    if (vt && matchMedia(MOTION).matches) vt.call(document, () => setPalette(true));
    else setPalette(true);
  };

  /** Type "objection" anywhere. */
  const overruled = () => {
    const el = root.current?.querySelector<HTMLElement>(".nb-egg");
    if (!el) return;
    el.hidden = false;
    if (!matchMedia(MOTION).matches) {
      setTimeout(() => (el.hidden = true), 1800);
      return;
    }
    gsap
      .timeline({ onComplete: () => void (el.hidden = true) })
      .fromTo(el.querySelector(".nb-egg-stamp"), { scale: 2.6, rotate: -22, opacity: 0 }, { scale: 1, rotate: -8, opacity: 1, duration: 0.32, ease: "power4.in" })
      // shake the overlay, never <main>: a transform there would break every fixed-position pin
      .fromTo(el, { x: -12 }, { x: 0, duration: 0.5, ease: "elastic.out(1.4,0.25)", clearProps: "x" }, ">-0.02")
      .fromTo(el.querySelector(".nb-egg-sub"), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.3 }, "<0.1")
      .to(el, { opacity: 0, duration: 0.4, delay: 1.3 })
      .set(el, { opacity: 1 });
  };

  useGSAP(
    () => {
      const el = root.current!;
      bindClock(el.querySelector(".nb-clock-t"), el.querySelector(".nb-clock-m"));
      const mm = gsap.matchMedia();

      /* ---- smooth scroll, sky, fly-through, velocity skew ---- */
      mm.add({ motion: MOTION, desktop: DESKTOP }, (ctx) => {
        if (!ctx.conditions!.motion) return;
        const lenis = new Lenis({ lerp: 0.085, smoothWheel: true });
        setLenis(lenis);
        lenis.on("scroll", ScrollTrigger.update);
        const tick = (t: number) => lenis.raf(t * 1000);
        gsap.ticker.add(tick);
        gsap.ticker.lagSmoothing(0);

        // velocity skew on headings and cards
        const skewers = gsap.utils.toArray<HTMLElement>("[data-skew]", el).map((n) =>
          gsap.quickTo(n, n.dataset.skew === "x" ? "skewX" : "skewY", { duration: 0.5, ease: "power3" }),
        );
        lenis.on("scroll", (l: Lenis) => {
          const v = gsap.utils.clamp(-4, 4, l.velocity * -0.14);
          skewers.forEach((s) => s(v));
        });

        // the sky: night → before dawn → first light (opacity only)
        gsap.to(".sky-stars", { yPercent: -18, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: true } });
        gsap.fromTo(".sky-pre", { opacity: 0 }, { opacity: 1, ease: "none", scrollTrigger: { trigger: "#casebot", start: "top 95%", end: "top 5%", scrub: true } });
        gsap.fromTo(".sky-dawn", { opacity: 0 }, { opacity: 1, ease: "none", scrollTrigger: { trigger: "#trust", start: "top bottom", end: "bottom 60%", scrub: true } });
        gsap.fromTo(".sky-stars", { opacity: 1 }, { opacity: 0.15, ease: "none", immediateRender: false, scrollTrigger: { trigger: "#casebot", start: "top bottom", end: "top top", scrub: true } });

        // the clock between the hero and the search scene (and on the way back up)
        ScrollTrigger.create({
          trigger: "#top",
          start: "top top",
          endTrigger: "#flight",
          end: "bottom top",
          onUpdate: (s) => setClock(clockAt("19:02", "19:40", s.progress), s.progress < 0.02 ? "cause list fetched" : "starting the search"),
        });

        // the document fly-through, loaded only now and only with WebGL
        const gl = el.querySelector<HTMLCanvasElement>(".nb-gl")!;
        let flight: { setProgress: (p: number) => void; setActive: (on: boolean) => void; dispose: () => void } | null = null;
        let dead = false;
        const probe = document.createElement("canvas");
        const hasGL = !!(probe.getContext("webgl2") || probe.getContext("webgl"));
        el.dataset.gl = hasGL ? "on" : "off";
        const st = ScrollTrigger.create({
          trigger: "#flight",
          start: "top bottom",
          end: "bottom top",
          onUpdate: (s) => {
            flight?.setProgress(s.progress);
            // fade in over the first fifth, out over the last
            gl.style.opacity = String(Math.min(1, s.progress * 5, (1 - s.progress) * 5));
          },
          onToggle: (s) => flight?.setActive(s.isActive),
        });
        if (hasGL) {
          const load = () =>
            import("./fx/doc-flight").then(({ createDocFlight }) => {
              if (dead) return;
              flight = createDocFlight(gl, { lite: !ctx.conditions!.desktop });
              flight.setProgress(st.progress);
              flight.setActive(st.isActive);
            });
          const ric = (window as Window & { requestIdleCallback?: (cb: () => void, o?: object) => number }).requestIdleCallback;
          if (ric) ric(load, { timeout: 1800 });
          else setTimeout(load, 900);
        }

        return () => {
          dead = true;
          flight?.dispose();
          gsap.ticker.remove(tick);
          lenis.destroy();
          setLenis(null);
        };
      });

      /* ---- custom cursor + magnetic buttons (fine pointers only) ---- */
      mm.add(`${MOTION} and ${FINE}`, () => {
        el.classList.add("has-cursor");
        const dot = el.querySelector<HTMLElement>(".nb-cursor-dot")!;
        const ring = el.querySelector<HTMLElement>(".nb-cursor-ring")!;
        const dx = gsap.quickTo(dot, "x", { duration: 0.08, ease: "none" });
        const dy = gsap.quickTo(dot, "y", { duration: 0.08, ease: "none" });
        const rx = gsap.quickTo(ring, "x", { duration: 0.45, ease: "power3" });
        const ry = gsap.quickTo(ring, "y", { duration: 0.45, ease: "power3" });
        const move = (e: PointerEvent) => {
          el.classList.add("cursor-live");
          dx(e.clientX);
          dy(e.clientY);
          rx(e.clientX);
          ry(e.clientY);
          const hot = (e.target as HTMLElement).closest?.("a, button, [role=option], .tk-card");
          el.classList.toggle("cursor-hot", !!hot);
        };
        window.addEventListener("pointermove", move);

        const mags = gsap.utils.toArray<HTMLElement>("[data-magnetic]", el).map((m) => {
          const mx = gsap.quickTo(m, "x", { duration: 0.6, ease: "elastic.out(1,0.4)" });
          const my = gsap.quickTo(m, "y", { duration: 0.6, ease: "elastic.out(1,0.4)" });
          const over = (e: PointerEvent) => {
            const r = m.getBoundingClientRect();
            mx((e.clientX - (r.left + r.width / 2)) * 0.35);
            my((e.clientY - (r.top + r.height / 2)) * 0.45);
          };
          const out = () => {
            mx(0);
            my(0);
          };
          m.addEventListener("pointermove", over);
          m.addEventListener("pointerleave", out);
          return () => {
            m.removeEventListener("pointermove", over);
            m.removeEventListener("pointerleave", out);
          };
        });
        return () => {
          el.classList.remove("has-cursor", "cursor-live");
          window.removeEventListener("pointermove", move);
          mags.forEach((off) => off());
        };
      });

      // Every scene has registered its pins by now (children's effects run
      // first); measure once more after webfonts settle line breaks.
      ScrollTrigger.refresh();
      document.fonts?.ready.then(() => ScrollTrigger.refresh());
    },
    { scope: root },
  );

  return (
    <div className="nb" ref={root}>
      <a className="nb-skip" href="#search">
        Skip to the features
      </a>

      <div className="nb-sky" aria-hidden="true">
        <div className="sky-night" />
        <div className="sky-stars" />
        <div className="sky-pre" />
        <div className="sky-dawn" />
      </div>
      <canvas className="nb-gl" aria-hidden="true" />

      <header className="nb-hdr">
        <div className="nb-wrap nb-nav">
          <Link className="nb-mark" href="/">
            Case&nbsp;Intel
          </Link>
          <nav className="nb-nav-right" aria-label="Primary">
            <button className="nb-k" type="button" onClick={openPalette} aria-keyshortcuts="Meta+K Control+K">
              <span>Demo</span>
              <kbd>{isMac ? "⌘" : "Ctrl"} K</kbd>
            </button>
            <a
              className="nb-nav-link nb-hide-sm"
              href="#trust"
              onClick={(e) => {
                e.preventDefault();
                scrollToTarget("#trust", { duration: 2 });
              }}
            >
              Trust
            </a>
            <AuthLink className="nb-login" />
          </nav>
        </div>
      </header>

      <div className="nb-clock" aria-hidden="true">
        <span className="nb-clock-t nb-mono">19:02</span>
        <span className="nb-clock-m nb-mono">cause list fetched</span>
      </div>

      <main className="nb-main">
        <Hero />
        <Flight />
        <FanOut />
        <OrderToTasks />
        <XRay />
        <CaseBot />
        <Toolkit />
        <Trust />
        <Finale />
      </main>

      <div className="nb-cursor-dot" aria-hidden="true" />
      <div className="nb-cursor-ring" aria-hidden="true" />

      <div className="nb-egg" hidden role="status">
        <div className="nb-egg-stamp">Overruled.</div>
        <div className="nb-egg-sub nb-mono">The objection is noted. Please continue scrolling, counsel.</div>
      </div>

      <CommandPalette open={palette} setOpen={setPalette} />
    </div>
  );
}
