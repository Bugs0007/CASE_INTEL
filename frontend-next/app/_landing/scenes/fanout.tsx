"use client";

import { useRef } from "react";
import { DISTRICTS, SEARCH_HITS, ADVOCATE } from "../data";
import { gsap, useGSAP, MOTION, DESKTOP, clockAt, setClock } from "../motion";
import { revealSplits } from "../fx/util";
import { SampleTag } from "../ui/bits";

const HUB = { x: 520, y: 330 };

// Complex positions: a small ring around each district's centre.
const NODES = DISTRICTS.map((d, di) => ({
  ...d,
  di,
  complexes: d.complexes.map((c, ci) => {
    const a = (ci / d.complexes.length) * Math.PI * 2 + di * 0.9;
    const r = d.complexes.length > 3 ? 40 : 34;
    return { ...c, x: d.x + Math.cos(a) * r, y: d.y + Math.sin(a) * r };
  }),
}));

const curve = (x1: number, y1: number, x2: number, y2: number) => {
  const mx = (x1 + x2) / 2 + (y2 - y1) * 0.18;
  const my = (y1 + y2) / 2 - (x2 - x1) * 0.18;
  return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`;
};

export function FanOut() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealSplits(root.current!);
      const mm = gsap.matchMedia();
      mm.add({ motion: MOTION, desktop: DESKTOP }, (ctx) => {
        if (!ctx.conditions!.motion) return;
        const el = root.current!;
        const q = gsap.utils.selector(el);
        const log = el.querySelector<HTMLElement>(".nb-fan-log-text")!;
        const N = NODES.length;

        // Start state: the whole constellation dark, nothing found yet.
        gsap.set(q(".nb-edge"), { strokeDashoffset: 1 });
        gsap.set(q(".nb-dnode-glow, .nb-cnode-lit, .nb-cnode-fail, .nb-dlabel"), { opacity: 0 });
        gsap.set(q(".nb-hit"), { opacity: 0, y: 14 });
        gsap.set(q(".nb-fan-done"), { opacity: 0, y: 10 });

        const STEP = 0.75;
        const failAt = 0.3 + NODES.findIndex((d) => d.complexes.some((c) => c.fails)) * STEP + 0.65;
        const tl = gsap.timeline({
          defaults: { ease: "none" },
          onUpdate: () => {
            const t = tl.time();
            const i = Math.max(0, Math.min(N - 1, Math.floor((t - 0.3) / STEP)));
            const d = NODES[i];
            const text =
              t > 0.3 + N * STEP
                ? "Run complete · results saved after every district"
                : `Scanning ${d.name} · ${d.complexes.map((c) => c.name).join(", ")}`;
            if (log.textContent !== text) log.textContent = text;
            el.classList.toggle("has-failed", t > failAt);
          },
          scrollTrigger: {
            id: "search",
            trigger: el,
            start: "top top",
            end: () => `+=${innerHeight * (ctx.conditions!.desktop ? 3.4 : 2.8)}`,
            pin: true,
            scrub: 0.7,
            invalidateOnRefresh: true,
            onUpdate: (st) => setClock(clockAt("19:40", "20:25", st.progress), "searching the state"),
          },
        });

        let placeholderGone = false;
        gsap.set(q(".nb-fan-wait"), { opacity: 1 });
        tl.to(q(".nb-hub-ring"), { scale: 1.6, opacity: 0, transformOrigin: "50% 50%", duration: 0.6, ease: "power2.out" }, 0);
        NODES.forEach((d, i) => {
          const at = 0.3 + i * STEP;
          tl.to(q(`.nb-edge--d${i}`), { strokeDashoffset: 0, duration: 0.5 }, at)
            .to(q(`.nb-dnode--${i} .nb-dnode-glow`), { opacity: 1, duration: 0.25 }, at + 0.4)
            .fromTo(q(`.nb-dnode--${i} .nb-dnode-core`), { scale: 0.6, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.3, ease: "back.out(3)" }, at + 0.4)
            .to(q(`.nb-dlabel--${i}`), { opacity: 1, duration: 0.25 }, at + 0.45)
            .to(q(`.nb-edge--c${i}`), { strokeDashoffset: 0, duration: 0.3, stagger: 0.06 }, at + 0.5);
          d.complexes.forEach((c, ci) => {
            const sel = `.nb-cnode--${i}-${ci}`;
            if (c.fails) {
              tl.to(q(`${sel} .nb-cnode-fail`), { opacity: 1, duration: 0.15 }, at + 0.65 + ci * 0.06).fromTo(
                q(`${sel} .nb-cnode-fail`),
                { scale: 2.2, transformOrigin: "50% 50%" },
                { scale: 1, duration: 0.3, ease: "power3.out" },
                "<",
              );
            } else {
              tl.to(q(`${sel} .nb-cnode-lit`), { opacity: 1, duration: 0.15 }, at + 0.65 + ci * 0.06);
            }
          });
          const hits = q(`.nb-hit[data-d="${d.name}"]`);
          if (hits.length) {
            tl.to(hits, { opacity: 1, y: 0, duration: 0.35, ease: "power2.out", stagger: 0.12 }, at + 0.7);
            if (!placeholderGone) {
              tl.to(q(".nb-fan-wait"), { opacity: 0, duration: 0.2 }, at + 0.6);
              placeholderGone = true;
            }
          }
        });
        tl.to(q(".nb-fan-done"), { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }, 0.3 + N * STEP + 0.2);
        tl.to({}, { duration: 0.6 });
      });
    },
    { scope: root },
  );

  return (
    <section className="nb-scene nb-fan" id="search" ref={root} aria-labelledby="nb-fan-h">
      <div className="nb-wrap nb-fan-grid">
        <div className="nb-copy">
          <p className="nb-eyebrow">01 · Find your matters</p>
          <h2 id="nb-fan-h" data-split>
            Search the whole state. <em>Not one court at a time.</em>
          </h2>
          <p className="nb-body">
            The eCourts advocate search covers one court complex at a time. Case Intel runs your name or bar code
            through every district and complex in the state, in the background, and hands you one list to import.
          </p>
          <ul className="nb-points nb-hide-sm">
            <li>One complex fails, the run carries on. Retry just the gaps later.</li>
            <li>Progress is saved after every district, so nothing found is lost.</li>
            <li>Every row is checked against the name you searched. Rows that can&apos;t be checked say so.</li>
          </ul>
        </div>

        <div className="nb-fan-stage">
          <div className="nb-stage-tags">
            <span className="nb-sample nb-sample--ghost">Abstract, not a map</span>
            <SampleTag>Sample run</SampleTag>
          </div>
          <svg className="nb-fan-svg" viewBox="0 0 1000 640" aria-hidden="true">
            {NODES.map((d, i) => (
              <path key={`e${i}`} className={`nb-edge nb-edge--d${i}`} d={curve(HUB.x, HUB.y, d.x, d.y)} pathLength={1} />
            ))}
            {NODES.map((d, i) =>
              d.complexes.map((c, ci) => (
                <path key={`c${i}-${ci}`} className={`nb-edge nb-edge--thin nb-edge--c${i}`} d={`M${d.x},${d.y} L${c.x},${c.y}`} pathLength={1} />
              )),
            )}
            <g className="nb-hub">
              <circle className="nb-hub-ring" cx={HUB.x} cy={HUB.y} r="16" />
              <circle className="nb-hub-core" cx={HUB.x} cy={HUB.y} r="6" />
            </g>
            {NODES.map((d, i) => (
              <g key={`d${i}`} className={`nb-dnode nb-dnode--${i}`}>
                <circle className="nb-dnode-glow" cx={d.x} cy={d.y} r="22" />
                <circle className="nb-dnode-core" cx={d.x} cy={d.y} r="5" />
                {d.complexes.map((c, ci) => (
                  <g key={ci} className={`nb-cnode nb-cnode--${i}-${ci}`}>
                    <circle className="nb-cnode-dim" cx={c.x} cy={c.y} r="3.2" />
                    <circle className="nb-cnode-lit" cx={c.x} cy={c.y} r="3.6" />
                    {c.fails ? (
                      <g className="nb-cnode-fail">
                        <circle cx={c.x} cy={c.y} r="9" />
                        <path d={`M${c.x - 4},${c.y - 4} L${c.x + 4},${c.y + 4} M${c.x + 4},${c.y - 4} L${c.x - 4},${c.y + 4}`} />
                      </g>
                    ) : null}
                  </g>
                ))}
              </g>
            ))}
            {NODES.map((d, i) => (
              <text key={`l${i}`} className={`nb-dlabel nb-dlabel--${i}`} x={d.x} y={d.y + (d.complexes.length > 3 ? 62 : 54)}>
                {d.name}
              </text>
            ))}
            <text className="nb-hub-label" x={HUB.x} y={HUB.y + 34}>
              {ADVOCATE}
            </text>
          </svg>
          <div className="nb-fan-log" aria-hidden="true">
            <span className="nb-fan-log-text">Run complete · results saved after every district</span>
            <span className="nb-fan-fail">Gajwel complex didn&apos;t answer · isolated, run continues</span>
          </div>
        </div>

        <div className="nb-fan-results">
          <div className="nb-panel-head">
            <span>Found under your name</span>
            <SampleTag />
          </div>
          <p className="nb-fan-wait nb-mono" aria-hidden="true">
            Matches land here as each district finishes…
          </p>
          {SEARCH_HITS.map((h) => (
            <div className="nb-hit" data-d={h.district} key={h.cn}>
              <div>
                <div className="nb-mono nb-hit-cn">{h.cn}</div>
                <div className="nb-hit-sub">
                  {h.court} · {h.parties}
                </div>
                <div className="nb-hit-adv">
                  Court record: <span className="nb-mono">{h.advocate || "(advocate cell blank)"}</span>
                </div>
              </div>
              {h.verified ? <span className="nb-chip nb-chip--ok">Name match</span> : <span className="nb-chip nb-chip--warn">Not verified</span>}
            </div>
          ))}
          <div className="nb-fan-done">
            <span className="nb-chip nb-chip--alert">1 complex failed</span>
            <span className="nb-retry">
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M13 8a5 5 0 1 1-1.5-3.6M13 2.5V5h-2.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
              </svg>
              Retry failed districts
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
