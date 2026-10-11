"use client";

import { useRef } from "react";
import { gsap, SplitText, useGSAP, MOTION, clockAt, setClock, scrollToTarget } from "../motion";
import { createDawn } from "../fx/dawn";
import { AuthLink, RequestAccess } from "../ui/bits";

export function Finale() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add(MOTION, () => {
        const el = root.current!;
        const q = gsap.utils.selector(el);
        const canvas = el.querySelector<HTMLCanvasElement>(".fin-gl")!;
        const dawn = createDawn(canvas);
        const night = el.querySelector<HTMLElement>(".fin-night")!;
        const sky = { p: 0 };
        if (dawn) night.style.display = "none";
        else canvas.style.display = "none";

        const split = SplitText.create(el.querySelector(".fin-h")!, { type: "lines", mask: "lines", linesClass: "nb-line" });
        gsap.set(split.lines, { yPercent: 115 });
        gsap.set(q(".fin-fade"), { opacity: 0, y: 24 });
        gsap.set(q(".fin-time"), { opacity: 0, scale: 1.25 });
        el.classList.add("is-night");

        const tl = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: {
            id: "finale",
            trigger: el,
            start: "top 85%",
            end: "bottom bottom",
            scrub: 0.6,
            onUpdate: (st) => {
              setClock(clockAt("09:50", "10:30", Math.min(1, st.progress * 1.6)), st.progress > 0.6 ? "court" : "before court");
              el.classList.toggle("is-night", sky.p < 0.55);
              document.documentElement.classList.toggle("nb-day", sky.p > 0.55);
            },
            onLeaveBack: () => document.documentElement.classList.remove("nb-day"),
          },
        });
        tl.to(sky, {
          p: 1,
          duration: 1,
          ease: "power1.inOut",
          onUpdate: () => {
            if (dawn) dawn.set(sky.p);
            else night.style.opacity = String(1 - sky.p);
          },
        })
          .to(q(".fin-time"), { opacity: 1, scale: 1, duration: 0.5, ease: "power2.out" }, 0.25)
          .to(split.lines, { yPercent: 0, duration: 0.5, stagger: 0.12, ease: "power3.out" }, 0.75)
          .to(q(".fin-fade"), { opacity: 1, y: 0, duration: 0.35, stagger: 0.08, ease: "power2.out" }, 1.05)
          .to({}, { duration: 0.35 });

        return () => {
          dawn?.dispose();
          split.revert();
          document.documentElement.classList.remove("nb-day");
        };
      });
    },
    { scope: root },
  );

  return (
    <>
      <section className="nb-finale" id="finale" ref={root} aria-labelledby="nb-fin-h">
        <div className="fin-stick">
          <canvas className="fin-gl" aria-hidden="true" />
          <div className="fin-night" aria-hidden="true" />
          <div className="nb-wrap fin-inner">
            <div className="fin-time nb-mono" aria-hidden="true">
              10:30
            </div>
            <h2 className="fin-h" id="nb-fin-h">
              Court Hall 3. Item 14. <em>You&apos;re ready.</em>
            </h2>
            <p className="fin-sub fin-fade">
              Case Intel is invite-only. Ask for an invitation, and bring your name or bar code. The search does the
              rest.
            </p>
            <div className="fin-cta fin-fade">
              <RequestAccess className="nb-btn nb-btn--solid nb-btn--xl" />
              <AuthLink className="nb-btn nb-btn--line" />
            </div>
            <p className="fin-note fin-fade">
              Or write to <a href="mailto:samallabhagath@gmail.com">samallabhagath@gmail.com</a>.
            </p>
          </div>
        </div>
      </section>

      <footer className="nb-footer">
        <div className="nb-wrap nb-foot">
          <span className="nb-mono">CASE INTEL · HYDERABAD</span>
          <span className="nb-foot-legal">
            Every name, case number, amount and document on this page is sample data. Case Intel is not affiliated with
            eCourts or with any court.
          </span>
          <a
            href="#top"
            className="nb-mono"
            onClick={(e) => {
              e.preventDefault();
              scrollToTarget(0, { duration: 2.4 });
            }}
          >
            Back to 19:02 ↑
          </a>
        </div>
      </footer>
    </>
  );
}
