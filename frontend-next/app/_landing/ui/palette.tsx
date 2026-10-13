"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";
import { ScrollTrigger, getLenis, scrollToTarget } from "../motion";

type Cmd = { id: string; group: string; label: string; hint: string; run: () => void };

/**
 * Plays a pinned scene like a film: jump to where its pin starts, then glide
 * to where it ends at a fixed pace, so the scrubbed timeline runs on its own.
 * Falls back to a plain jump when the scene isn't pinned (reduced motion,
 * phones for the horizontal section).
 */
function play(id: string, anchor: string, seconds: number) {
  const st = ScrollTrigger.getById(id);
  const lenis = getLenis();
  if (!st || !lenis) {
    scrollToTarget(anchor);
    return;
  }
  lenis.scrollTo(st.start, {
    duration: 1.2,
    force: true,
    onComplete: () => lenis.scrollTo(st.end, { duration: seconds, easing: (t: number) => t, force: true }),
  });
}

export function CommandPalette({ open, setOpen }: { open: boolean; setOpen: (v: boolean) => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const restore = useRef<HTMLElement | null>(null);

  const close = useCallback(() => {
    const done = () => setOpen(false);
    const vt = (document as Document & { startViewTransition?: (cb: () => void) => unknown }).startViewTransition;
    if (vt && matchMedia("(prefers-reduced-motion: no-preference)").matches) vt.call(document, done);
    else done();
    restore.current?.focus();
  }, [setOpen]);

  const cmds: Cmd[] = useMemo(
    () => [
      { id: "p-search", group: "Play a scene", label: "Watch a state-wide search run", hint: "Scene 01", run: () => play("search", "#search", 9) },
      { id: "p-orders", group: "Play a scene", label: "Turn a scanned order into tasks", hint: "Scene 02", run: () => play("orders", "#orders", 10) },
      { id: "p-xray", group: "Play a scene", label: "X-ray the 06:30 cause list", hint: "Scene 03", run: () => play("xray", "#causelist", 8) },
      { id: "p-bot", group: "Play a scene", label: "Ask Case Bot a question", hint: "Scene 04", run: () => play("casebot", "#casebot", 8) },
      { id: "p-desk", group: "Play a scene", label: "Pan across the rest of the desk", hint: "Scene 05", run: () => play("desk", "#desk", 9) },
      { id: "g-top", group: "Go to", label: "19:02 · The cause list arrives", hint: "Top", run: () => scrollToTarget(0, { duration: 2 }) },
      { id: "g-trust", group: "Go to", label: "Whose file is it", hint: "Trust", run: () => scrollToTarget("#trust", { duration: 2 }) },
      { id: "g-fin", group: "Go to", label: "10:30 · Court", hint: "Finale", run: () => scrollToTarget("#finale", { duration: 2.4, offset: innerHeight * 0.9 }) },
      { id: "a-req", group: "Act", label: "Create an account", hint: "Google", run: () => router.push("/register") },
      {
        id: "a-login",
        group: "Act",
        label: typeof window !== "undefined" && getToken() ? "Open dashboard" : "Log in",
        hint: "App",
        run: () => router.push(getToken() ? "/dashboard" : "/login"),
      },
    ],
    [router],
  );

  const shown = cmds.filter((c) => (c.label + " " + c.group + " " + c.hint).toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    if (!open) return;
    restore.current = document.activeElement as HTMLElement | null;
    setQuery("");
    setActive(0);
    requestAnimationFrame(() => input.current?.focus());
    getLenis()?.stop();
    return () => getLenis()?.start();
  }, [open]);

  if (!open) return null;

  const runAt = (i: number) => {
    const c = shown[i];
    if (!c) return;
    setOpen(false);
    getLenis()?.start();
    requestAnimationFrame(() => c.run());
  };

  let lastGroup = "";
  return (
    <div className="pal-scrim" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="pal" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="pal-in">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
            <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.3" />
          </svg>
          <input
            ref={input}
            value={query}
            placeholder="Play a scene, jump to a time, create an account…"
            aria-label="Search commands"
            aria-controls="pal-list"
            aria-activedescendant={shown[active] ? `pal-${shown[active].id}` : undefined}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(shown.length - 1, a + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(0, a - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                runAt(active);
              } else if (e.key === "Escape") {
                e.preventDefault();
                close();
              } else if (e.key === "Tab") {
                e.preventDefault(); // focus stays in the dialog; arrows move the selection
              }
            }}
          />
          <kbd>esc</kbd>
        </div>
        <ul className="pal-list" id="pal-list" role="listbox">
          {shown.length === 0 ? <li className="pal-empty">Nothing matches. Try &ldquo;cause list&rdquo;.</li> : null}
          {shown.map((c, i) => {
            const head = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            return (
              <li key={c.id} role="presentation">
                {head ? <div className="pal-group nb-mono">{head}</div> : null}
                <div
                  id={`pal-${c.id}`}
                  role="option"
                  aria-selected={i === active}
                  className={`pal-item${i === active ? " is-on" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => runAt(i)}
                >
                  <span>{c.label}</span>
                  <span className="pal-hint nb-mono">{c.hint}</span>
                </div>
              </li>
            );
          })}
        </ul>
        <div className="pal-foot nb-mono">
          <span>↑↓ move · ↵ run</span>
          <span>Sample data throughout</span>
        </div>
      </div>
    </div>
  );
}
