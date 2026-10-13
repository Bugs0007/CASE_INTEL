"use client";

import { useRef } from "react";
import { XRAY_ROWS, CAUSE_LIST } from "../data";
import { gsap, useGSAP, MOTION, DESKTOP, clockAt, setClock } from "../motion";
import { revealSplits } from "../fx/util";
import { SampleTag } from "../ui/bits";

// Column x-offsets "detected" on this sample sheet (pt). Per-document, never
// hardcoded, is the point; the numbers are just what this sheet measures.
const COLS = [
  { key: "S.No.", x: "5%", pt: "36.8" },
  { key: "Case", x: "15.5%", pt: "112.4" },
  { key: "Parties", x: "44%", pt: "318.0" },
];

export function XRay() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealSplits(root.current!);
      const mm = gsap.matchMedia();
      mm.add({ motion: MOTION, desktop: DESKTOP }, (ctx) => {
        if (!ctx.conditions!.motion) return;
        const el = root.current!;
        const q = gsap.utils.selector(el);
        const sheet = el.querySelector<HTMLElement>(".xr-sheet")!;
        const snos = q(".xr-sno") as HTMLElement[];
        // In text order a serial number floats free of its row; drawn here as
        // sitting off its case's baseline until the positional read pairs them.
        const gap = (i: number) => snos[i].parentElement!.clientHeight * 0.42;

        // The overnight jump: the clock spins from tonight to 06:30 as the
        // scene arrives, while the giant time settles behind it.
        gsap.timeline({
          scrollTrigger: {
            trigger: el,
            start: "top bottom",
            end: "top top",
            scrub: 0.5,
            onUpdate: (st) => setClock(clockAt("21:40", "06:30", st.progress), st.progress < 0.98 ? "overnight" : "re-reading the list"),
          },
        }).fromTo(q(".xr-time"), { scale: 1.5, opacity: 0, yPercent: 20 }, { scale: 1, opacity: 1, yPercent: 0, ease: "power2.out" });

        gsap.set(q(".xr-reveal"), { yPercent: -100 });
        gsap.set(q(".xr-reveal-in"), { yPercent: 100 });
        gsap.set(q(".xr-box, .xr-collabel, .xr-link, .xr-hl, .xr-listed, .xr-result, .xr-strike, .xr-bypos"), { opacity: 0 });
        gsap.set(q(".xr-link, .xr-hl, .xr-strike"), { scaleX: 0 });
        gsap.set(snos, { y: (i) => -gap(i) });

        const tl = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: {
            id: "xray",
            trigger: el,
            start: "top top",
            end: () => `+=${innerHeight * (ctx.conditions!.desktop ? 3.2 : 2.6)}`,
            pin: true,
            scrub: 0.7,
            invalidateOnRefresh: true,
            onUpdate: () => setClock("06:30", "re-reading the list"),
          },
        });

        // the beam sweeps; the coordinate layer is revealed exactly behind it
        tl.fromTo(q(".xr-beam"), { y: 0, opacity: 0 }, { opacity: 1, duration: 0.1 }, 0.2)
          .to(q(".xr-beam"), { y: () => sheet.clientHeight, duration: 2 }, 0.2)
          .to(q(".xr-reveal"), { yPercent: 0, duration: 2 }, 0.2)
          .to(q(".xr-reveal-in"), { yPercent: 0, duration: 2 }, 0.2)
          .to(q(".xr-beam"), { opacity: 0, duration: 0.15 }, 2.15);
        q(".xr-row").forEach((row: Element, i: number) => {
          tl.to(row.querySelectorAll(".xr-box"), { opacity: 1, duration: 0.12, stagger: 0.03 }, 0.45 + i * 0.28);
        });
        tl.to(q(".xr-collabel"), { opacity: 1, y: 0, stagger: 0.08, duration: 0.3, ease: "back.out(2)" }, 2.25)
          // the serial numbers drop onto their case numbers' baselines
          .to(snos, { y: 0, duration: 0.55, stagger: 0.05, ease: "back.out(2.2)" }, 2.75)
          .to(q(".xr-link"), { opacity: 1, scaleX: 1, duration: 0.3, stagger: 0.05, ease: "power2.out" }, 3.1)
          .to(q(".xr-strike"), { opacity: 1, scaleX: 1, duration: 0.4, ease: "power2.inOut" }, 2.9)
          .to(q(".xr-naive"), { opacity: 0.35, duration: 0.3 }, 3.2)
          .to(q(".xr-bypos"), { opacity: 1, duration: 0.3 }, 3.3)
          // and item 14 resolves to a plain answer
          .to(q(".xr-hl"), { opacity: 1, scaleX: 1, duration: 0.5, ease: "expo.out" }, 3.7)
          .to(q(".xr-listed"), { opacity: 1, duration: 0.3 }, 3.9)
          .fromTo(q(".xr-result"), { y: 20 }, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }, 4.1)
          .to({}, { duration: 0.7 });
      });
    },
    { scope: root },
  );

  return (
    <section className="nb-scene nb-xray" id="causelist" ref={root} aria-labelledby="nb-xray-h">
      <div className="xr-time" aria-hidden="true">
        06:30
      </div>
      <div className="nb-wrap nb-xray-grid">
        <div className="nb-copy">
          <p className="nb-eyebrow">03 · 06:30, the list is read again</p>
          <h2 id="nb-xray-h" data-split>
            A misread column looks exactly like <em>&ldquo;not listed.&rdquo;</em>
          </h2>
          <p className="nb-body">
            So the cause-list PDF isn&apos;t read in text order. Every character is placed by its position on the page,
            the columns are found afresh in each document, and each serial number is paired with its case by height.
          </p>
          <ul className="nb-points nb-hide-sm">
            <li>The real lists come in at least three layouts. No column position is hardcoded.</li>
            <li>&ldquo;None of your matters are listed&rdquo; is the one wrong answer this must never give.</li>
            <li>Read at 19:00, read again at 06:30. The Telangana High Court, most other High Courts and the District Courts.</li>
          </ul>
        </div>

        <div className="xr-stage">
          <div className="xr-naive" aria-hidden="true">
            <span className="xr-naive-lbl">Read in text order</span>
            <span className="nb-mono xr-naive-txt">
              {XRAY_ROWS.map((r) => r.sno).join(" ")} {XRAY_ROWS.map((r) => r.cn).join(" ")}
            </span>
            <i className="xr-strike" />
          </div>
          <div className="xr-bypos nb-mono" aria-hidden="true">
            Read by position → {XRAY_ROWS.map((r) => `${r.sno} ${r.cn}`).slice(1, 4).join(" · ")} …
          </div>

          <div className="xr-sheet" role="img" aria-label="Sample cause-list page; item 14, WP/14562/2024, found listed in Court Hall 3">
            <div className="xr-sheet-head">
              <span>CAUSE LIST · {CAUSE_LIST.hall.toUpperCase()}</span>
              <span>02.09.2026</span>
            </div>
            <div className="xr-cols nb-mono">
              <span style={{ left: COLS[0].x }}>S.NO.</span>
              <span style={{ left: COLS[1].x }}>CASE NO.</span>
              <span style={{ left: COLS[2].x }}>PARTIES</span>
            </div>
            <div className="xr-rows">
              {XRAY_ROWS.map((r) => (
                <div className={`xr-row${r.mine ? " is-mine" : ""}`} key={r.sno}>
                  <i className="xr-hl" aria-hidden="true" />
                  <span className="xr-sno nb-mono" style={{ left: COLS[0].x }}>
                    {r.sno}
                    <i className="xr-box" />
                  </span>
                  <i className="xr-link" aria-hidden="true" />
                  <span className="xr-case" style={{ left: COLS[1].x }}>
                    <span className="xr-cn nb-mono">
                      {r.cn}
                      <i className="xr-box" />
                    </span>
                  </span>
                  <span className="xr-parties" style={{ left: COLS[2].x }}>
                    {r.parties}
                    <i className="xr-box" />
                  </span>
                  {r.mine ? <b className="xr-listed">Listed</b> : null}
                </div>
              ))}
            </div>

            {/* the coordinate layer, revealed behind the beam by two opposing transforms */}
            <div className="xr-reveal" aria-hidden="true">
              <div className="xr-reveal-in">
                {COLS.map((c) => (
                  <div className="xr-colline" key={c.key} style={{ left: c.x }}>
                    <span className="xr-collabel">
                      {c.key} · x {c.pt}
                    </span>
                  </div>
                ))}
                <div className="xr-gridlines" />
              </div>
            </div>
            <div className="xr-beam" aria-hidden="true" />
          </div>

          <div className="xr-result">
            <span className="nb-chip nb-chip--ok">Listed</span>
            <span>
              <b className="nb-mono">Item 14</b> · {CAUSE_LIST.hall} · <span className="nb-mono">WP/14562/2024</span>
            </span>
            <SampleTag />
          </div>
        </div>
      </div>
    </section>
  );
}
