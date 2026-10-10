"use client";

import { useRef } from "react";
import { CAUSE_LIST } from "../data";
import { gsap, SplitText, useGSAP, MOTION, DESKTOP, setClock } from "../motion";
import { noiseOut, scramble } from "../fx/util";
import { AuthLink, RequestAccess, SampleTag } from "../ui/bits";

export function Hero() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add(MOTION, () => {
        const el = root.current!;
        setClock(CAUSE_LIST.fetched, "cause list fetched");

        /* --- intro: the list resolves out of noise --- */
        const cells = gsap.utils.toArray<HTMLElement>("[data-scramble]", el);
        cells.forEach(noiseOut);
        const others = gsap.utils.toArray<HTMLElement>(".nb-lrow:not(.is-mine)", el);
        const mine = gsap.utils.toArray<HTMLElement>(".nb-lrow.is-mine", el);

        gsap.set(others, { opacity: 1 });
        const split = SplitText.create(el.querySelector(".nb-h1")!, { type: "lines", mask: "lines", linesClass: "nb-line" });
        const intro = gsap.timeline({ delay: 0.15 });
        el.classList.add("is-ready");
        intro
          .from(split.lines, { yPercent: 115, duration: 1.3, stagger: 0.12, ease: "expo.out" }, 0)
          .from(".nb-hero-copy .nb-fade", { y: 18, opacity: 0, duration: 0.9, stagger: 0.08, ease: "power3.out" }, 0.45)
          .from(".nb-list", { opacity: 0, y: 30, duration: 1, ease: "power3.out" }, 0.2);
        // every row decodes; the advocate's own rows lock last and light up
        others.forEach((row, i) => {
          row.querySelectorAll<HTMLElement>("[data-scramble]").forEach((c) => intro.add(scramble(c, { duration: 0.9 }), 0.5 + i * 0.05));
          intro.to(row, { opacity: 0.38, duration: 0.6 }, 1.1 + i * 0.04);
        });
        mine.forEach((row, i) => {
          row.querySelectorAll<HTMLElement>("[data-scramble]").forEach((c) => intro.add(scramble(c, { duration: 1.2, settle: 0.7 }), 1.0 + i * 0.25));
          intro
            .fromTo(row.querySelector(".nb-lrow-bar"), { scaleX: 0 }, { scaleX: 1, duration: 0.9, ease: "expo.out" }, 2.0 + i * 0.22)
            .from(row.querySelector(".nb-yours"), { opacity: 0, x: -10, duration: 0.5, ease: "back.out(2)" }, 2.3 + i * 0.22);
        });
        intro.from(".nb-list-foot", { opacity: 0, duration: 0.6 }, 2.6);

        /* --- first scroll: the hero tips back and flies away --- */
        const out = gsap.timeline({
          scrollTrigger: { trigger: el, start: "top top", end: "bottom top", scrub: 0.6 },
        });
        out
          .to(".nb-hero-copy", { yPercent: -28, opacity: 0, ease: "none" }, 0)
          .to(".nb-list", { scale: 1.32, rotateX: 22, yPercent: -18, opacity: 0, ease: "power1.in" }, 0)
          .to(".nb-cue", { opacity: 0, duration: 0.15 }, 0);

        return () => split.revert();
      });

      // Desktop: the cursor tilts the list a few degrees. Fine pointers only.
      mm.add(`${MOTION} and ${DESKTOP} and (pointer: fine)`, () => {
        const list = root.current!.querySelector<HTMLElement>(".nb-list-tilt")!;
        const rx = gsap.quickTo(list, "rotationX", { duration: 0.8, ease: "power3" });
        const ry = gsap.quickTo(list, "rotationY", { duration: 0.8, ease: "power3" });
        const move = (e: PointerEvent) => {
          rx(((e.clientY / innerHeight) - 0.5) * -6);
          ry(((e.clientX / innerWidth) - 0.5) * 8);
        };
        window.addEventListener("pointermove", move);
        return () => window.removeEventListener("pointermove", move);
      });
    },
    { scope: root },
  );

  return (
    <section className="nb-hero" id="top" ref={root} aria-labelledby="nb-hero-h">
      <div className="nb-wrap nb-hero-grid">
        <div className="nb-hero-copy">
          <p className="nb-eyebrow nb-fade">For advocates practising before Indian courts</p>
          <h1 className="nb-h1" id="nb-hero-h">
            Tonight&apos;s cause list. <em>Already read.</em>
          </h1>
          <p className="nb-lede nb-fade">
            Case Intel reads the Telangana High Court cause list at 19:00 and again at 06:30, finds your matters on it,
            and carries each one forward: the order that followed, what your side must do, the fee it earned.
          </p>
          <div className="nb-cta nb-fade">
            <RequestAccess />
            <AuthLink className="nb-btn nb-btn--line" />
          </div>
          <p className="nb-note nb-fade">Invite-only. Telangana High Court cause lists today; more courts as they are added.</p>
        </div>

        <div className="nb-list-wrap">
          <div className="nb-list-tilt">
            <div className="nb-list" role="table" aria-label="Sample cause list with the advocate's two matters highlighted">
              <div className="nb-list-head" role="rowgroup">
                <div className="nb-list-title">
                  <span>Cause list · {CAUSE_LIST.hall}</span>
                  <span className="nb-dim">{CAUSE_LIST.court}</span>
                </div>
                <div className="nb-list-meta">
                  <span className="nb-live">
                    <i className="nb-pulse" aria-hidden="true" />
                    fetched {CAUSE_LIST.fetched}
                  </span>
                  <SampleTag />
                </div>
              </div>
              <div className="nb-list-cols" role="row" aria-hidden="true">
                <span>Item</span>
                <span>Case</span>
                <span className="nb-hide-sm">Parties</span>
                <span>Advocate</span>
              </div>
              <div role="rowgroup">
                {CAUSE_LIST.rows.map((r) => (
                  <div className={`nb-lrow${r.mine ? " is-mine" : ""}`} role="row" key={r.item}>
                    <i className="nb-lrow-bar" aria-hidden="true" />
                    <span className="nb-mono" role="cell" data-scramble>
                      {r.item}
                    </span>
                    <span className="nb-mono" role="cell" data-scramble>
                      {r.cn}
                    </span>
                    <span className="nb-hide-sm nb-parties" role="cell">
                      {r.parties}
                    </span>
                    <span className="nb-adv" role="cell">
                      <span data-scramble>{r.adv}</span>
                      {r.mine ? <b className="nb-yours">yours</b> : null}
                    </span>
                  </div>
                ))}
              </div>
              <div className="nb-list-foot">
                <span>For {CAUSE_LIST.date}</span>
                <span>
                  Your matters · <b>Item 14</b> · <b>Item 18</b>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="nb-cue" aria-hidden="true">
        <span>Scroll</span>
        <i />
      </div>
    </section>
  );
}

/**
 * The fly-through between the hero and the search scene. The WebGL canvas
 * itself is fixed and owned by the page root (it needs to sit behind
 * everything); this section only provides the scroll distance, the line of
 * copy mid-flight, and the static fallback composition.
 */
export function Flight() {
  const root = useRef<HTMLElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add(MOTION, () => {
        const spans = gsap.utils.toArray<HTMLElement>(".nb-flight-line > span", root.current!);
        const tl = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: { trigger: root.current, start: "top 60%", end: "bottom 40%", scrub: 0.5 },
        });
        spans.forEach((s, i) => {
          tl.fromTo(s, { opacity: 0, yPercent: 60, scale: 0.92 }, { opacity: 1, yPercent: 0, scale: 1, duration: 0.5 }, i * 0.35);
        });
        tl.to(spans, { opacity: 0, yPercent: -40, duration: 0.5, stagger: 0.08 }, ">0.6");
      });
    },
    { scope: root },
  );
  return (
    <section className="nb-flight" id="flight" ref={root} aria-label="Every district, every court complex, one search">
      <div className="nb-flight-stick">
        <div className="nb-flight-static" aria-hidden="true">
          {Array.from({ length: 7 }, (_, i) => (
            <i key={i} className={`nb-sheet nb-sheet--${i}`} />
          ))}
        </div>
        <p className="nb-flight-line">
          <span>Every district.</span>
          <span>Every court complex.</span>
          <span>
            <em>One search.</em>
          </span>
        </p>
      </div>
    </section>
  );
}
