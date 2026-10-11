"use client";

import { useRef } from "react";
import { BOT, CASE } from "../data";
import { gsap, ScrollTrigger, SplitText, useGSAP, MOTION, DESKTOP, clockAt, setClock } from "../motion";
import { revealSplits } from "../fx/util";
import { SampleTag } from "../ui/bits";

/**
 * Beams are drawn in stage pixels. Their end points are measured, never
 * animated (only opacity/dashoffset move), so a re-measure on every
 * ScrollTrigger refresh keeps them glued to the documents at any width.
 */
function layoutBeams(stage: HTMLElement) {
  const S = stage.getBoundingClientRect();
  stage.querySelectorAll<SVGSVGElement>(".cb-beams").forEach((svg) => svg.setAttribute("viewBox", `0 0 ${S.width} ${S.height}`));
  const pt = (el: Element, ax: number, ay: number) => {
    const r = el.getBoundingClientRect();
    return { x: r.left - S.left + r.width * ax, y: r.top - S.top + r.height * ay };
  };
  const curve = (a: { x: number; y: number }, b: { x: number; y: number }) => {
    const my = (a.y + b.y) / 2;
    return `M${a.x},${a.y} C${a.x},${my} ${b.x},${my} ${b.x},${b.y}`;
  };
  const qBox = stage.querySelector(".cb-q")!;
  const origin = pt(qBox, 0.5, 1);
  stage.querySelectorAll<SVGPathElement>("[data-beam]").forEach((p) => {
    const target = stage.querySelector(p.dataset.beam!);
    if (target) p.setAttribute("d", curve(origin, pt(target, 0.5, 0)));
  });
  stage.querySelectorAll<SVGPathElement>("[data-cite]").forEach((p) => {
    const chip = stage.querySelector(`.cb-cite[data-c="${p.dataset.cite}"]`);
    const hit = stage.querySelector(`.cb-hit[data-ref="${p.dataset.cite}"]`);
    if (chip && hit) p.setAttribute("d", curve(pt(chip, 0.5, 0), pt(hit, 0.5, 1)));
  });
}

export function CaseBot() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealSplits(root.current!);
      // Beams are measured in every mode, so the static fallback draws them too.
      const stage = root.current!.querySelector<HTMLElement>(".cb-stage")!;
      const relayout = () => layoutBeams(stage);
      relayout();
      ScrollTrigger.addEventListener("refresh", relayout);
      window.addEventListener("resize", relayout);
      const mm = gsap.matchMedia();
      mm.add({ motion: MOTION, desktop: DESKTOP }, (ctx) => {
        if (!ctx.conditions!.motion) return;
        const el = root.current!;
        const q = gsap.utils.selector(el);

        const chars = SplitText.create(el.querySelector(".cb-q-text")!, { type: "words,chars" }).chars;
        gsap.set(chars, { opacity: 0 });
        gsap.set(q(".cb-beam, .cb-citeline"), { strokeDashoffset: 1 });
        gsap.set(q(".cb-hit-mark, .cb-status, .cb-block, .cb-cite, .cb-word"), { opacity: 0 });
        gsap.set(q(".cb-doc"), { opacity: 0.45 });

        const tl = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: {
            id: "casebot",
            trigger: el,
            start: "top top",
            end: () => `+=${innerHeight * (ctx.conditions!.desktop ? 3.2 : 2.6)}`,
            pin: true,
            scrub: 0.7,
            invalidateOnRefresh: true,
            onUpdate: (st) => setClock(clockAt("06:50", "07:05", st.progress), "preparing"),
          },
        });

        tl.to(chars, { opacity: 1, duration: 0.02, stagger: 0.022 }, 0.1)
          .to(q(".cb-status"), { opacity: 1, duration: 0.2 }, chars.length * 0.022 + 0.2)
          .to(q(".cb-beam--hit"), { strokeDashoffset: 0, duration: 0.7, stagger: 0.12, ease: "power2.inOut" }, ">")
          .to(q(".cb-beam--miss"), { strokeDashoffset: 0, duration: 0.7, stagger: 0.12, ease: "power2.inOut" }, "<")
          .to(q(".cb-doc"), { opacity: 1, duration: 0.3, stagger: 0.05 }, "<0.3")
          .to(q(".cb-hit-mark"), { opacity: 1, duration: 0.3, stagger: 0.15 }, ">-0.1")
          .to(q(".cb-block"), { opacity: 1, duration: 0.3 }, "<")
          .to(q(".cb-word"), { opacity: 1, duration: 0.05, stagger: 0.035 }, ">0.2")
          .to(q(".cb-cite"), { opacity: 1, duration: 0.2, stagger: 0.1 }, "<0.3")
          .to(q(".cb-citeline"), { strokeDashoffset: 0, duration: 0.6, stagger: 0.12, ease: "power2.inOut" }, ">")
          .to({}, { duration: 0.7 });
      });
      return () => {
        ScrollTrigger.removeEventListener("refresh", relayout);
        window.removeEventListener("resize", relayout);
      };
    },
    { scope: root },
  );

  return (
    <section className="nb-scene nb-casebot" id="casebot" ref={root} aria-labelledby="nb-cb-h">
      <div className="nb-wrap nb-cb-grid">
        <div className="nb-copy">
          <p className="nb-eyebrow">04 · Ask the file</p>
          <h2 id="nb-cb-h" data-split>
            Ask your case file a question. <em>Get the page it came from.</em>
          </h2>
          <p className="nb-body">
            Case Bot answers from the documents uploaded to your case, with citations back to the passages it used. It
            searches by meaning and by keyword together, then reranks what it found.
          </p>
          <ul className="nb-points nb-hide-sm">
            <li>Every retrieval step is filtered to your own documents, not just the screen you see.</li>
            <li>If the owner filter is missing, the search refuses to run at all.</li>
            <li>When the best match is weak, the answer says so.</li>
          </ul>
        </div>

        <div className="cb-stage">
          <svg className="cb-beams" aria-hidden="true">
            {BOT.docs.map((d, i) => (
              <path
                key={d.name}
                className={`cb-beam ${d.hit ? "cb-beam--hit" : "cb-beam--miss"}`}
                data-beam={`.cb-doc--${i} ${d.hit ? ".cb-hit" : ".cb-doc-name"}`}
                pathLength={1}
              />
            ))}
            <path className="cb-beam cb-beam--miss cb-beam--blocked" data-beam=".cb-fence-edge" pathLength={1} />
          </svg>
          <svg className="cb-beams cb-beams--under" aria-hidden="true">
            <path className="cb-citeline" data-cite="1" pathLength={1} />
            <path className="cb-citeline" data-cite="2" pathLength={1} />
          </svg>

          <div className="cb-q">
            <span className="cb-q-lbl">
              Case Bot · <span className="nb-mono">{CASE.cn}</span>
            </span>
            <p className="cb-q-text">{BOT.question}</p>
            <span className="cb-status nb-mono">Searching your documents only</span>
          </div>

          <div className="cb-docs">
            {BOT.docs.map((d, i) => (
              <div className={`cb-doc cb-doc--${i}${d.hit ? " has-hit" : ""}`} key={d.name}>
                <span className="cb-doc-name nb-mono">{d.name}</span>
                <span className="cb-lines" aria-hidden="true" />
                {d.hit ? (
                  <span className="cb-hit" data-ref={d.ref}>
                    <i className="cb-hit-mark" aria-hidden="true" />
                    <sup className="nb-mono">[{d.ref}]</sup> {d.hit}
                  </span>
                ) : (
                  <span className="cb-lines cb-lines--short" aria-hidden="true" />
                )}
              </div>
            ))}
            <div className="cb-fence">
              <span className="cb-fence-edge" aria-hidden="true" />
              <span className="cb-fence-lbl">Another advocate&apos;s documents</span>
              <span className="cb-fence-sub nb-mono">never searched · never cited</span>
              <span className="cb-block nb-mono">owner filter</span>
            </div>
          </div>

          <div className="cb-answer">
            <div className="nb-panel-head">
              <span>Answer</span>
              <SampleTag />
            </div>
            <p>
              {BOT.answer.map((part, i) =>
                part.c ? (
                  <sup className="cb-cite nb-mono" data-c={part.c} key={i}>
                    {part.t}
                  </sup>
                ) : (
                  part.t.split(/(\s+)/).map((w, j) =>
                    /\s+/.test(w) ? (
                      w
                    ) : (
                      <span className={`cb-word${part.b ? " is-b" : ""}`} key={`${i}-${j}`}>
                        {w}
                      </span>
                    ),
                  )
                ),
              )}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
