"use client";

import { useRef } from "react";
import { CASE, INVOICE, ORDER, TRAVEL } from "../data";
import { gsap, useGSAP, MOTION, DESKTOP, FINE, clockAt, setClock } from "../motion";
import { revealSplits } from "../fx/util";
import { SampleTag } from "../ui/bits";

type Card = { key: string; label: string; title: string; body: string; visual: React.ReactNode };

const CARDS: Card[] = [
  {
    key: "prep",
    label: "Hearing prep sheet",
    title: "One page before you walk in.",
    body: "The cause-list slot, the last order, open tasks and documents on one PDF, with a short state-of-the-matter paragraph. It is cached, and written again only when the facts change.",
    visual: (
      <div className="tk-pdf">
        <div className="tk-pdf-h">
          <b>Prep sheet</b>
          <span className="nb-mono">{CASE.cn}</span>
        </div>
        <dl>
          <dt>Cause list</dt>
          <dd className="nb-mono">Item 14 · Court Hall 3</dd>
          <dt>Last order</dt>
          <dd>{ORDER.happened}</dd>
          <dt>Open tasks</dt>
          <dd>File proof of deposit · <span className="nb-mono">02 Sep</span></dd>
        </dl>
        <div className="tk-pdf-para">
          <span className="tk-pdf-lbl">State of the matter</span>
          <i />
          <i />
          <i className="is-short" />
        </div>
      </div>
    ),
  },
  {
    key: "conflict",
    label: "Conflict check at intake",
    title: "Same party, other side. You hear about it first.",
    body: "A new matter's parties are compared with your own cases for the same party on opposite sides. It warns and asks you to acknowledge; it never hard-blocks, and never looks at another advocate's cases.",
    visual: (
      <div className="tk-conflict">
        <div className="tk-field">
          <span>New matter · your client</span>
          <b>S. Anil</b>
        </div>
        <div className="tk-warn">
          <span className="nb-chip nb-chip--warn">Possible conflict</span>
          <p>
            <b>S. Anil</b> is the <u>opposite party</u> in your <span className="nb-mono">OS/1120/2023</span>.
          </p>
          <span className="tk-ack">
            <i /> I&apos;ve reviewed this. Continue.
          </span>
        </div>
      </div>
    ),
  },
  {
    key: "limitation",
    label: "Limitation deadlines",
    title: "The earliest possible date, not the most hopeful one.",
    body: "Periods come from a rules table written into the code. The computation is conservative: the earliest possible date, with Section 12(2), 4 and 5 caveats stated as notes rather than applied. You add them; nothing fires on its own.",
    visual: (
      <div className="tk-limit">
        <span className="tk-limit-lbl">Earliest possible date</span>
        <b className="nb-mono tk-limit-date">14 Oct 2026</b>
        <ul>
          <li>
            <span className="nb-mono">s.12(2)</span> Time to obtain a certified copy: noted, not added
          </li>
          <li>
            <span className="nb-mono">s.4</span> Court closed on the last day: noted, not applied
          </li>
          <li>
            <span className="nb-mono">s.5</span> Condonation of delay: noted, not assumed
          </li>
        </ul>
      </div>
    ),
  },
  {
    key: "fees",
    label: "Appearance-fee invoices",
    title: "Every appearance ends as a PDF you can send.",
    body: "A fee moves Pending, Invoiced, Paid, and each invoice is numbered in your own running series. Appearance, hotel, flight or other, several to a hearing.",
    visual: (
      <div className="tk-fee">
        <div className="tk-steps">
          <span className="is-done">Pending</span>
          <span className="is-done">Invoiced</span>
          <span className="is-now">Paid</span>
        </div>
        <div className="tk-inv">
          <div className="tk-inv-h">
            <b>Invoice</b>
            <span className="nb-mono">{INVOICE.number}</span>
          </div>
          <div className="tk-inv-row">
            <span>Appearance · {INVOICE.hearing}</span>
            <span className="nb-mono">{INVOICE.amount}</span>
          </div>
          <div className="tk-inv-row tk-inv-row--dim">
            <span>Bill to</span>
            <span>{INVOICE.billTo}</span>
          </div>
          <span className="tk-inv-pdf nb-mono">PDF</span>
        </div>
      </div>
    ),
  },
  {
    key: "travel",
    label: "Travel",
    title: "The ticket lives with the hearing.",
    body: "Tickets and stays uploaded against the hearing, so everything for an outstation date sits in one place.",
    visual: (
      <div className="tk-travel">
        {TRAVEL.map((t) => (
          <div className="tk-trip" key={t.file}>
            <span className="tk-trip-kind nb-mono">{t.kind}</span>
            <span>{t.label}</span>
            <span className="nb-mono tk-trip-file">{t.file}</span>
          </div>
        ))}
        <div className="tk-drop">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 11V3M4.5 6.5 8 3l3.5 3.5M3 13h10" fill="none" stroke="currentColor" strokeWidth="1.3" />
          </svg>
          Upload against <span className="nb-mono">02 Sep 2026</span>
        </div>
      </div>
    ),
  },
];

export function Toolkit() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealSplits(root.current!);
      const mm = gsap.matchMedia();

      // Desktop: pin the section and turn vertical scroll into a horizontal pan.
      mm.add(`${MOTION} and ${DESKTOP}`, () => {
        const el = root.current!;
        const track = el.querySelector<HTMLElement>(".tk-track")!;
        const dist = () => track.scrollWidth - el.clientWidth;
        const pan = gsap.to(track, {
          x: () => -dist(),
          ease: "none",
          scrollTrigger: {
            id: "desk",
            trigger: el,
            start: "top top",
            end: () => `+=${dist()}`,
            pin: true,
            scrub: 0.8,
            invalidateOnRefresh: true,
            onUpdate: (st) => setClock(clockAt("07:10", "09:30", st.progress), "the rest of the desk"),
          },
        });
        // each card's contents parallax against the pan
        gsap.utils.toArray<HTMLElement>(".tk-visual", el).forEach((v) => {
          gsap.fromTo(
            v,
            { xPercent: 10 },
            {
              xPercent: -10,
              ease: "none",
              scrollTrigger: { trigger: v.closest(".tk-card"), containerAnimation: pan, start: "left right", end: "right left", scrub: true },
            },
          );
        });
      });

      // Phones: a native, swipeable scroll-snap row. Clock still advances.
      mm.add(`${MOTION} and (max-width: 767px)`, () => {
        const el = root.current!;
        gsap.timeline({
          scrollTrigger: {
            trigger: el,
            start: "top 70%",
            end: "bottom 30%",
            onUpdate: (st) => setClock(clockAt("07:10", "09:30", st.progress), "the rest of the desk"),
          },
        });
      });

      // Cursor tilt + glare on fine pointers.
      mm.add(`${MOTION} and ${FINE}`, () => {
        const cards = gsap.utils.toArray<HTMLElement>(".tk-card-in", root.current!);
        const offs = cards.map((c) => {
          const rx = gsap.quickTo(c, "rotationX", { duration: 0.6, ease: "power3" });
          const ry = gsap.quickTo(c, "rotationY", { duration: 0.6, ease: "power3" });
          const glare = c.querySelector<HTMLElement>(".tk-glare")!;
          const gx = gsap.quickTo(glare, "x", { duration: 0.4, ease: "power3" });
          const gy = gsap.quickTo(glare, "y", { duration: 0.4, ease: "power3" });
          const move = (e: PointerEvent) => {
            const r = c.getBoundingClientRect();
            const px = (e.clientX - r.left) / r.width - 0.5;
            const py = (e.clientY - r.top) / r.height - 0.5;
            rx(py * -9);
            ry(px * 11);
            gx((px + 0.5) * r.width);
            gy((py + 0.5) * r.height);
            gsap.to(glare, { opacity: 1, duration: 0.3, overwrite: "auto" });
          };
          const leave = () => {
            rx(0);
            ry(0);
            gsap.to(glare, { opacity: 0, duration: 0.5, overwrite: "auto" });
          };
          c.addEventListener("pointermove", move);
          c.addEventListener("pointerleave", leave);
          return () => {
            c.removeEventListener("pointermove", move);
            c.removeEventListener("pointerleave", leave);
          };
        });
        return () => offs.forEach((off) => off());
      });
    },
    { scope: root },
  );

  return (
    <section className="nb-scene nb-desk" id="desk" ref={root} aria-labelledby="nb-desk-h">
      <div className="tk-track">
        <div className="tk-intro">
          <p className="nb-eyebrow">05 · The rest of the desk</p>
          <h2 id="nb-desk-h" data-split>
            Everything else the morning needs. <em>Already on the hearing.</em>
          </h2>
          <p className="nb-body">Five more things that used to live in a diary, a folder and the margin of a cause list.</p>
          <span className="tk-hint nb-mono" aria-hidden="true">
            <span className="tk-hint-desk">Keep scrolling →</span>
            <span className="tk-hint-touch">Swipe for five more →</span>
          </span>
        </div>
        {CARDS.map((c, i) => (
          <article className={`tk-card tk-card--${c.key}`} key={c.key} data-skew="x">
            <div className="tk-card-in">
              <i className="tk-glare" aria-hidden="true" />
              <div className="tk-card-top">
                <span className="nb-mono">0{i + 1}</span>
                <span>{c.label}</span>
              </div>
              <div className="tk-visual">
                {c.visual}
                <SampleTag />
              </div>
              <h3>{c.title}</h3>
              <p>{c.body}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
