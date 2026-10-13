"use client";

import { useRef } from "react";
import { gsap, useGSAP, MOTION, clockAt, setClock } from "../motion";
import { revealSplits } from "../fx/util";

const PILLARS = [
  {
    k: "Sign-in",
    t: "One account, one advocate.",
    b: "Sign up with Google, or from an invitation link with a username and password. Google sends Case Intel your name and verified email address, never your Google password.",
  },
  {
    k: "Per-advocate isolation",
    t: "Every record has an owner.",
    b: "Cases, documents, hearings, fees: each row carries its owner, and every list, view and edit is filtered to the advocate signed in. A test fails if a new endpoint is added without being scoped or deliberately reviewed.",
  },
  {
    k: "Owner-scoped retrieval",
    t: "Case Bot only searches your documents.",
    b: "The search takes the owner as a required input and filters every leg by it, meaning and keyword alike. Narrowing to one case narrows within your documents; it never replaces the owner filter.",
  },
];

const WONT = [
  "It won't read cause lists for seven High Courts (Allahabad, Gujarat, Himachal Pradesh, Jharkhand, Kerala, Madhya Pradesh, Punjab & Haryana) or the Madurai bench of Madras. The eCourts portal serves no usable list for them, so those matters say \u201cNot covered\u201d rather than \u201cNot listed.\u201d",
  "It doesn't track Supreme Court cases.",
  "It won't tell two advocates with the same name apart. It shows the court's own record and lets you judge.",
  "It won't hard-block a conflict. It warns; you decide.",
  "It won't apply limitation exceptions for you. Sections 12(2), 4 and 5 stay as notes.",
  "It won't send routine adjournment orders to the AI at all.",
  "It won't file anything on your behalf.",
  "It isn't affiliated with eCourts or with any court.",
];

// A field of records; a third of them are "yours". Deterministic so server
// and client render the same pattern.
const CELLS = Array.from({ length: 72 }, (_, i) => ((i * 37 + 11) % 7) < 2 || i % 11 === 3);

export function Trust() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealSplits(root.current!);
      const mm = gsap.matchMedia();
      mm.add(MOTION, () => {
        const el = root.current!;
        const q = gsap.utils.selector(el);
        gsap.timeline({
          scrollTrigger: {
            trigger: el,
            start: "top 70%",
            end: "bottom 60%",
            scrub: 0.6,
            onUpdate: (st) => setClock(clockAt("09:30", "09:50", st.progress), "before court"),
          },
        })
          .from(q(".tr-cell.is-mine"), { opacity: 0.08, scale: 0.4, stagger: { each: 0.02, from: "random" }, ease: "power2.out" }, 0);

        gsap.from(q(".tr-pillar"), {
          y: 40,
          opacity: 0,
          stagger: 0.12,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: { trigger: q(".tr-pillars")[0], start: "top 80%" },
        });
        gsap.from(q(".tr-wont li"), {
          opacity: 0,
          x: -16,
          stagger: 0.07,
          duration: 0.7,
          ease: "power2.out",
          scrollTrigger: { trigger: q(".tr-wont")[0], start: "top 80%" },
        });
      });
    },
    { scope: root },
  );

  return (
    <section className="nb-trust" id="trust" ref={root} aria-labelledby="nb-trust-h">
      <div className="nb-wrap">
        <div className="tr-head">
          <div>
            <p className="nb-eyebrow">06 · Whose file is it</p>
            <h2 id="nb-trust-h" data-split data-skew="y">
              Every matter has an owner. <em>Every query asks who&apos;s asking.</em>
            </h2>
          </div>
          <div className="tr-field" aria-hidden="true">
            <div className="tr-grid">
              {CELLS.map((mine, i) => (
                <i key={i} className={`tr-cell${mine ? " is-mine" : ""}`} />
              ))}
            </div>
            <span className="tr-field-lbl nb-mono">
              each square, one record · <b>lit: yours</b> · dark: someone else&apos;s, never returned
            </span>
          </div>
        </div>

        <div className="tr-pillars">
          {PILLARS.map((p) => (
            <article className="tr-pillar" key={p.k}>
              <span className="tr-k nb-mono">{p.k}</span>
              <h3>{p.t}</h3>
              <p>{p.b}</p>
            </article>
          ))}
        </div>

        <div className="tr-wont">
          <h3>What it won&apos;t do</h3>
          <ul>
            {WONT.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
