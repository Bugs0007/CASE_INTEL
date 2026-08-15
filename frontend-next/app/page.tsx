// app/page.tsx — Case Intel landing page (App Router)
// Requires: import "./landing.css" (below) and the fonts registered in layout.tsx.

"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getToken } from "@/lib/auth";
import "./landing.css";

/* ------------------------------------------------------------------ */

type Line = { k: string; s: string; chip?: [string, "ok" | "pending" | "alert" | "none"]; v?: string };

const PANELS: {
  title: string;
  live: string;
  lines: Line[];
  foot?: [string, string];
  bar?: boolean;
  summary?: { text: string; you: string; them: string };
}[] = [
  {
    title: "Advocate search · Telangana",
    live: "running",
    lines: [
      { k: "WP/14882/2025", s: "High Court for the State of Telangana", chip: ["match", "ok"] },
      { k: "CC/331/2024", s: "Hyderabad · CMM Court Complex", chip: ["match", "ok"] },
      { k: "OS/2210/2023", s: "Ranga Reddy · District Court Complex", chip: ["match", "ok"] },
      { k: "EP/94/2022", s: "Medchal–Malkajgiri · Kukatpally", chip: ["skipped", "none"] },
    ],
    foot: ["Districts scanned", "33 / 33"],
    bar: true,
  },
  {
    title: "Cause list · 12 Aug 2026",
    live: "fetched 19:02",
    lines: [
      { k: "WP/14882/2025", s: "Court No. 4 · Division Bench", v: "Item 27" },
      { k: "CRP/887/2025", s: "Court No. 12 · Single Judge", v: "Item 6" },
      { k: "WA/402/2026", s: "Supplementary list", chip: ["not listed", "none"] },
      { k: "CC/331/2024", s: "District court · list not yet published", chip: ["pending", "pending"] },
    ],
    foot: ["List types read", "8 / 8"],
    bar: true,
  },
  {
    title: "Hearing · 21 Nov 2025",
    live: "order attached",
    lines: [{ k: "order_5_2025-11-21.pdf", s: "CRP/887/2025 · 4 pages", chip: ["open", "ok"] }],
    summary: {
      text:
        "Interim suspension of the trial court's order continued. Both sides directed to complete pleadings before the next date.",
      you: "File rejoinder within four weeks",
      them: "File counter-affidavit; serve copy in advance",
    },
    foot: ["Next hearing", "08 Jan 2027"],
  },
  {
    title: "Fees · CRP/887/2025",
    live: "up to date",
    lines: [
      { k: "Appearance · 21 Nov 2025", s: "Invoice CI/2026/0114", chip: ["paid", "ok"] },
      { k: "Appearance · 14 Aug 2025", s: "Invoice CI/2026/0098", chip: ["invoiced", "alert"] },
      { k: "Appearance · 02 Jun 2025", s: "Not yet invoiced", chip: ["pending", "none"] },
      { k: "Travel · Vijayawada", s: "Ticket and stay uploaded", chip: ["on file", "ok"] },
    ],
    foot: ["Billed contact", "Primary · 1 of 3"],
  },
];

const STEPS = [
  {
    label: "Find",
    title: "Search the state, not one court at a time.",
    body:
      "Enter an advocate name or bar code and Case Intel fans out across every district and court complex in the state, then hands you the list. Tick the matters that are yours and import them.",
    points: [
      "Runs in the background — close the tab, results keep landing",
      "Failed districts retried on their own, not the whole search",
      "Party role read from eCourts, so petitioner and respondent are never mixed up",
    ],
  },
  {
    label: "Appear",
    title: "Tomorrow's board, the evening before.",
    body:
      "Cause lists are pulled every night and again at 6:30 in the morning, across all eight list types — so you know the court and the item number while there's still time to prepare for it.",
    points: [
      "Reads the published PDFs directly, captcha and all",
      "Not listed is stated plainly, never guessed",
      "A hearing already marked listed is never quietly downgraded",
    ],
  },
  {
    label: "Record",
    title: "The order lands on the hearing that produced it.",
    body:
      "Each order PDF attaches itself to the right date on the right case. Open it in one click, or read the overview first — what the court held, and what each side now has to do.",
    points: [
      "Overview written once at ingest, so it opens instantly",
      "Framed from your side of the cause title",
      "Downloads stay behind your login",
    ],
  },
  {
    label: "Bill",
    title: "Every appearance ends as a number you can send.",
    body:
      "Appearance fees move from pending to invoiced to paid, with the invoice generated for you and numbered in your own running series. Travel and stay for outstation matters sit on the same hearing.",
    points: [
      "Invoice numbers never collide, even on simultaneous entries",
      "Marked paid only after an invoice exists",
      "Tickets and hotel confirmations upload against the hearing",
    ],
  },
];

const MY_CASES = [
  ["WP/14882/2025", "High Court for the State of Telangana", "12 Aug · Item 27", "Listed", "listed"],
  ["CC/331/2024", "XIV Addl. Chief Metropolitan Magistrate, Hyderabad", "19 Aug", "Awaiting list", "await"],
  ["OS/2210/2023", "III Addl. District Judge, Ranga Reddy", "03 Sep", "Awaiting list", "await"],
  ["CRP/887/2025", "High Court for the State of Telangana", "21 Nov · disposed", "Fee paid", "listed"],
];

/* ------------------------------------------------------------------ */

function Panel({ i, mobile = false }: { i: number; mobile?: boolean }) {
  const p = PANELS[i];
  return (
    <div className={mobile ? "lp-card lp-card--inline" : "lp-card"} data-panel={i}>
      <div className="lp-card-top">
        <span className="lp-card-title">{p.title}</span>
        <span className="lp-card-live">
          <i className="lp-dot" />
          {p.live}
        </span>
      </div>

      {p.lines.map((l) => (
        <div className="lp-line" key={l.k}>
          <div>
            <div className="lp-k">{l.k}</div>
            <div className="lp-s">{l.s}</div>
          </div>
          {l.v ? <span className="lp-v">{l.v}</span> : null}
          {l.chip ? <span className={`ci-chip ci-chip--${l.chip[1]}`}>{l.chip[0]}</span> : null}
        </div>
      ))}

      {p.summary ? (
        <div className="lp-summary">
          <div className="lp-summary-lbl">Order overview</div>
          <p>{p.summary.text}</p>
          <div className="lp-party">
            <div>
              <span>You — petitioner</span>
              {p.summary.you}
            </div>
            <div>
              <span>Respondent</span>
              {p.summary.them}
            </div>
          </div>
        </div>
      ) : null}

      {p.foot ? (
        <>
          <div className="lp-scan">
            <span>{p.foot[0]}</span>
            <span>{p.foot[1]}</span>
          </div>
          {p.bar ? (
            <div className="lp-bar">
              <i />
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export default function Landing() {
  const [stuck, setStuck] = useState(false);
  const [active, setActive] = useState(0);
  const [rowsIn, setRowsIn] = useState(false);
  // A logged-in advocate can reach "/" too (it's public, not just the
  // signed-out landing page) -- rather than bouncing them, swap the login
  // CTAs for a direct link back into the app so returning here never reads
  // as a dead end.
  const [loggedIn, setLoggedIn] = useState(false);
  const heroRef = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    setLoggedIn(!!getToken());
  }, []);

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > window.innerHeight * 0.55);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setRowsIn(true), 250);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step));
        }),
      { rootMargin: "-45% 0px -45% 0px" }
    );
    stepRefs.current.forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            obs.unobserve(e.target);
          }
        }),
      { threshold: 0.2 }
    );
    document.querySelectorAll(".lp-reveal").forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  return (
    <div className="lp">
      <header className={`lp-hdr ${stuck ? "stuck" : "ci-on-field"}`}>
        <div className="lp-wrap lp-nav">
          <Link className="lp-mark" href="/">
            <span className="lp-mark-name">Case&nbsp;Intel</span>
            <span className="lp-mark-sub">eCourts</span>
          </Link>
          <nav className="lp-nav-right">
            <span className="lp-nav-links">
              <a className="lp-nav-link" href="#what">What it does</a>
              <a className="lp-nav-link" href="#register">Under it</a>
            </span>
            {loggedIn ? (
              <Link className="lp-login" href="/dashboard">Open dashboard</Link>
            ) : (
              <Link className="lp-login" href="/login">Log in</Link>
            )}
          </nav>
        </div>
      </header>

      {/* HERO */}
      <div className="lp-hero ci-on-field" ref={heroRef}>
        <div className="lp-wrap lp-hero-inner">
          <div className="ci-eyebrow">For advocates practising before Indian courts</div>
          <h1 className="lp-h1">
            Your cases arrive from eCourts. Everything after that <em>happens here.</em>
          </h1>
          <p className="lp-lede">
            Search by advocate name or bar code, import the matters that are yours, and let Case Intel
            carry each one forward — tomorrow&apos;s item number, the order that followed, and the fee
            it earned.
          </p>
          <div className="lp-cta">
            {loggedIn ? (
              <Link className="ci-btn ci-btn--solid" href="/dashboard">Open dashboard</Link>
            ) : (
              <Link className="ci-btn ci-btn--solid" href="/login">Log in</Link>
            )}
            <a className="ci-btn ci-btn--line" href="#what">See what it does</a>
          </div>

          <div className="lp-record">
            <div className="lp-record-head">
              <span>MY CASES</span>
              <span>ADVOCATE <b>bar code AP/1274/2011</b></span>
              <span>SYNCED <b>07:02</b></span>
            </div>
            {MY_CASES.map(([cn, ct, dt, tag, tone], i) => (
              <div
                className={`lp-row ${rowsIn ? "in" : ""}`}
                key={cn}
                style={{ transitionDelay: `${i * 130}ms` }}
              >
                <span className="lp-cn">{cn}</span>
                <span className="lp-ct">{ct}</span>
                <span className="lp-dt">{dt}</span>
                <span className={`lp-tag lp-tag--${tone}`}>{tag}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* WHAT IT DOES */}
      <section className="lp-features" id="what">
        <div className="lp-wrap">
          <div className="lp-sechead lp-reveal">
            <div className="ci-eyebrow">What it does</div>
            <h2>Four things, in the order a matter actually moves.</h2>
            <p>
              No manual CNR entry, no separate diary, no chasing a clerk for the item number the night
              before.
            </p>
          </div>

          <div className="lp-grid">
            <div className="lp-steps">
              {STEPS.map((s, i) => (
                <article
                  className={`lp-step ${active === i ? "on" : ""}`}
                  data-step={i}
                  key={s.label}
                  ref={(el) => {
                    stepRefs.current[i] = el;
                  }}
                >
                  <div className="lp-step-no">{s.label}</div>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                  <ul>
                    {s.points.map((pt) => (
                      <li key={pt}>{pt}</li>
                    ))}
                  </ul>
                  <Panel i={i} mobile />
                </article>
              ))}
            </div>

            <div className="lp-stage" aria-hidden="true">
              {PANELS.map((_, i) => (
                <div className={`lp-stage-slot ${active === i ? "on" : ""}`} key={i}>
                  <Panel i={i} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* UNDER IT */}
      <div className="lp-strip" id="register">
        <div className="lp-wrap">
          <div className="lp-sechead lp-reveal">
            <div className="ci-eyebrow">Under it</div>
            <h2>Built the boring way, on purpose.</h2>
          </div>
          <div className="lp-strip-grid">
            {[
              ["8", "cause-list types read every night, not just the daily list"],
              ["2×", "daily fetch — 7:00 pm and 6:30 am, before and after publication"],
              ["33", "districts covered in a single state-wide advocate search"],
              ["1", "account per advocate. Your cases are visible to you and no one else"],
            ].map(([n, l]) => (
              <div className="lp-strip-item lp-reveal" key={l}>
                <div className="lp-n">{n}</div>
                <div className="lp-l">{l}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CLOSE */}
      <section className="lp-close ci-on-field">
        <div className="lp-wrap">
          <div className="ci-eyebrow">Access</div>
          <h2>Bring your bar code. The rest is already on record.</h2>
          <p>
            Case Intel is open to a small set of practices while cause-list coverage widens court by
            court. If you already have an account, pick up where the register left off.
          </p>
          <div className="lp-cta">
            {loggedIn ? (
              <Link className="ci-btn ci-btn--solid" href="/dashboard">Open dashboard</Link>
            ) : (
              <Link className="ci-btn ci-btn--solid" href="/login">Log in</Link>
            )}
            <a className="ci-btn ci-btn--line" href="mailto:samallabhagath@gmail.com">Request access</a>
          </div>
          <p className="lp-cta-note">
            Or email <a href="mailto:samallabhagath@gmail.com">samallabhagath@gmail.com</a> directly to
            request access.
          </p>
        </div>
      </section>

      <footer className="lp-footer ci-on-field">
        <div className="lp-wrap lp-foot">
          <span>CASE INTEL · HYDERABAD</span>
          <a href="#top">Back to top</a>
        </div>
      </footer>
    </div>
  );
}
