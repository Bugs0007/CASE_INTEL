"use client";

import { useRef } from "react";
import { CASE, ORDER, CAL_DAYS } from "../data";
import { gsap, useGSAP, MOTION, DESKTOP, clockAt, setClock } from "../motion";
import { offsetWithin, revealSplits } from "../fx/util";
import { SampleTag } from "../ui/bits";

function OrderSheet() {
  return (
    <div className="nb-sheet-body">
      <div className="nb-sheet-court">
        IN THE HIGH COURT FOR THE STATE OF TELANGANA
        <br />
        AT HYDERABAD
      </div>
      <div className="nb-sheet-sub">(Special Original Jurisdiction)</div>
      <div className="nb-sheet-sub">WEDNESDAY, THE TWENTY NINTH DAY OF JULY, TWO THOUSAND AND TWENTY SIX</div>
      <div className="nb-sheet-present">PRESENT: {ORDER.bench.toUpperCase()}</div>
      <div className="nb-sheet-cn">WRIT PETITION No. 14562 OF 2024</div>
      <div className="nb-sheet-parties">
        <span>{CASE.title.split(" vs. ")[0]}</span>
        <i>…Petitioner</i>
        <span>AND</span>
        <span>TSSPDCL</span>
        <i>…Respondent</i>
      </div>
      <div className="nb-sheet-order">ORDER:</div>
      {ORDER.paragraphs.map((p, i) => (
        <p key={i} className={`nb-sheet-p${i === 2 ? " is-yours" : ""}${i === 3 ? " is-theirs" : ""}`}>
          <span className="nb-hilite" aria-hidden="true" />
          <span className="nb-sheet-no">{i + 1}.</span> {p}
        </p>
      ))}
      <div className="nb-sheet-sign">
        <svg viewBox="0 0 120 30" aria-hidden="true">
          <path d="M4 22c10-14 14-16 16-8s-4 12 4 4 12-14 14-6-2 10 6 4 14-8 20-6 10 4 16 0 14-6 34-2" fill="none" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        <span>SD/- K.S.J · //TRUE COPY//</span>
      </div>
      <div className="nb-stamp" aria-hidden="true">
        CERTIFIED
        <br />
        COPY
      </div>
    </div>
  );
}

export function OrderToTasks() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealSplits(root.current!);
      const mm = gsap.matchMedia();
      mm.add({ motion: MOTION, desktop: DESKTOP }, (ctx) => {
        if (!ctx.conditions!.motion) return;
        const el = root.current!;
        const q = gsap.utils.selector(el);
        const stage = el.querySelector<HTMLElement>(".nb-order-stage")!;
        const flyers = q(".nb-fly") as HTMLElement[];
        const sources = q(".nb-due") as HTMLElement[];
        const targets = q(".nb-cal-slot.is-target") as HTMLElement[];

        // Each flying chip starts on its due-date chip in the card and lands
        // in its calendar cell. Offsets ignore transforms, so these stay
        // right however far through the timeline a refresh happens.
        const from = (i: number) => offsetWithin(sources[i], stage);
        const to = (i: number) => offsetWithin(targets[i], stage);

        gsap.set(q(".nb-must, .nb-cal"), { opacity: 0 });
        gsap.set(q(".nb-must"), { y: 40, scale: 0.97 });
        gsap.set(q(".nb-cal"), { y: 30 });
        gsap.set(q(".nb-hilite"), { scaleX: 0 });
        gsap.set(q(".nb-cal-task"), { opacity: 0 });
        gsap.set(flyers, { opacity: 0, x: (i) => from(i).x, y: (i) => from(i).y, transformOrigin: "0 0" });

        const tl = gsap.timeline({
          defaults: { ease: "power2.inOut" },
          scrollTrigger: {
            id: "orders",
            trigger: el,
            start: "top top",
            end: () => `+=${innerHeight * (ctx.conditions!.desktop ? 4.2 : 3.4)}`,
            pin: true,
            scrub: 0.8,
            invalidateOnRefresh: true,
            onUpdate: (st) => setClock(clockAt("21:10", "21:40", st.progress), "reading tonight's order"),
          },
        });

        // 1. the sheet lifts off the desk, still folded in thirds
        tl.fromTo(
          q(".nb-paper-lift"),
          { rotateX: 62, rotateZ: -9, yPercent: 18, scale: 0.74 },
          { rotateX: 0, rotateZ: -1.5, yPercent: 0, scale: 1, duration: 1.1, ease: "power3.out" },
          0,
        )
          .fromTo(q(".nb-paper-shadow"), { opacity: 0.9, scale: 0.8 }, { opacity: 0.45, scale: 1.08, duration: 1.1 }, 0)
          // 2. and unfolds: bottom third first, then the top
          .fromTo(q(".nb-fold--bot"), { rotateX: 176 }, { rotateX: 0, duration: 0.9, ease: "power3.inOut" }, 1.0)
          .fromTo(q(".nb-fold--top"), { rotateX: -176 }, { rotateX: 0, duration: 0.9, ease: "power3.inOut" }, 1.55)
          .to(q(".nb-paper-lift"), { rotateZ: 0, duration: 0.6 }, 2.2)
          // 3. the two directions get marked: yours in amber, theirs in grey
          .to(q(".is-yours .nb-hilite"), { scaleX: 1, duration: 0.6, ease: "power2.out" }, 2.6)
          .to(q(".is-theirs .nb-hilite"), { scaleX: 1, duration: 0.5, ease: "power2.out" }, 2.95)
          // 4. the paper gives way to what it means for you
          .to(q(".nb-paper-lift"), { scale: 0.9, yPercent: -6, opacity: 0, duration: 0.8 }, 3.6)
          .to(q(".nb-paper-shadow, .nb-paper-zone > .nb-sample"), { opacity: 0, duration: 0.6 }, 3.6)
          .to(q(".nb-must"), { opacity: 1, y: 0, scale: 1, duration: 0.8, ease: "power3.out" }, 3.85)
          .from(q(".nb-must-row"), { opacity: 0, x: -14, stagger: 0.12, duration: 0.5 }, 4.15)
          // 5. and your two tasks fly onto the calendar
          .to(q(".nb-cal"), { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, 4.8);

        flyers.forEach((f, i) => {
          const at = 5.3 + i * 0.35;
          const toX = () => to(i).x + (to(i).w - f.offsetWidth * 0.62) / 2;
          const toY = () => to(i).y + (to(i).h - f.offsetHeight * 0.62) / 2;
          tl.to(f, { opacity: 1, duration: 0.1 }, at)
            .fromTo(
              f,
              { x: () => from(i).x, y: () => from(i).y, scale: 1 },
              { x: toX, y: toY, scale: 0.62, duration: 0.9, ease: "power3.inOut", immediateRender: false },
              at,
            )
            .to(f, { opacity: 0, duration: 0.15 }, at + 0.9)
            .to(q(`.nb-cal-task--${i}`), { opacity: 1, duration: 0.2 }, at + 0.95);
        });
        tl.to({}, { duration: 0.8 });
      });
    },
    { scope: root },
  );

  return (
    <section className="nb-scene nb-order" id="orders" ref={root} aria-labelledby="nb-order-h">
      <div className="nb-wrap nb-order-grid">
        <div className="nb-copy">
          <p className="nb-eyebrow">02 · Read the order</p>
          <h2 id="nb-order-h" data-split>
            The order arrives as a scan. <em>You get what you must do.</em>
          </h2>
          <p className="nb-body">
            Each order PDF is summarised once, when it arrives: what the court did, then your side&apos;s directions,
            kept apart from the other side&apos;s. Your directions become tasks with due dates.
          </p>
          <ul className="nb-points nb-hide-sm">
            <li>Due dates come from a fixed table of phrases like &ldquo;within four weeks&rdquo;, not from the AI.</li>
            <li>Unreadable, very short or routine adjournment orders skip the AI entirely.</li>
            <li>Only your side&apos;s directions become tasks, and only once your party role is known.</li>
          </ul>
        </div>

        <div className="nb-order-stage">
          <div className="nb-paper-zone">
            <div className="nb-paper-shadow" aria-hidden="true" />
            <div className="nb-paper-lift">
              <div className="nb-paper" role="img" aria-label={`Sample scanned order in ${CASE.cn}, dated ${ORDER.date}`}>
                {(["top", "mid", "bot"] as const).map((f) => (
                  <div className={`nb-fold nb-fold--${f}`} key={f}>
                    <div className="nb-fold-face">
                      <OrderSheet />
                    </div>
                    <div className="nb-fold-back">
                      {f === "top" ? (
                        <div className="nb-docket" aria-hidden="true">
                          <span>W.P. No. 14562 of 2024</span>
                          <b>ORDER</b>
                          <span>dt. 29.07.2026</span>
                          <i>Certified copy · sample</i>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <SampleTag>Sample order</SampleTag>
          </div>

          <div className="nb-must">
            <div className="nb-panel-head">
              <span>
                Order overview · <span className="nb-mono">{ORDER.date}</span>
              </span>
              <SampleTag />
            </div>
            <p className="nb-must-what">{ORDER.happened}</p>
            <div className="nb-must-side">You · {CASE.side}</div>
            {ORDER.yours.map((d) => (
              <div className="nb-must-row" key={d.text}>
                <span>{d.text}</span>
                <span className="nb-due">
                  <b className="nb-mono">{d.due}</b>
                  <i>{d.rule}</i>
                </span>
              </div>
            ))}
            <div className="nb-must-side nb-must-side--them">Respondent · not your task</div>
            {ORDER.theirs.map((t) => (
              <div className="nb-must-row nb-must-row--them" key={t}>
                <span>{t}</span>
              </div>
            ))}
            <div className="nb-must-next">
              Next date <span className="nb-mono">{ORDER.next}</span>
            </div>
          </div>

          <div className="nb-cal" aria-label="Your tasks on the calendar">
            <div className="nb-cal-head">
              <span>Tasks · your side only</span>
              <span className="nb-mono">24 Aug – 06 Sep 2026</span>
            </div>
            <div className="nb-cal-grid">
              {CAL_DAYS.map((d) => {
                const ti = ORDER.yours.findIndex((y) => y.dueKey === d.key);
                return (
                  <div className={`nb-cal-day${d.dow === "Sun" ? " is-off" : ""}`} key={d.key}>
                    <span className="nb-cal-dow">{d.dow}</span>
                    <span className="nb-mono nb-cal-n">{d.day}</span>
                    {d.key === "2026-09-02" ? <span className="nb-cal-hearing">Hearing</span> : null}
                    <span className={`nb-cal-slot${ti >= 0 ? " is-target" : ""}`}>
                      {ti >= 0 ? <i className={`nb-cal-task nb-cal-task--${ti}`}>{ti === 0 ? "Deposit" : "Proof"}</i> : null}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {ORDER.yours.map((d, i) => (
            <span className="nb-fly" key={i} aria-hidden="true">
              {i === 0 ? "Deposit" : "File proof"} · {d.due}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
