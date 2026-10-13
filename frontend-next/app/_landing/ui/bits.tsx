"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth";

export const REQUEST_ACCESS = "mailto:samallabhagath@gmail.com";

/** Every panel of invented data carries this. */
export function SampleTag({ children = "Sample data" }: { children?: string }) {
  return <span className="nb-sample">{children}</span>;
}

/**
 * A logged-in advocate can reach "/" too. Rather than bouncing them, the
 * login CTA becomes a link back into the app (same rule as before).
 */
export function useLoggedIn() {
  const [loggedIn, setLoggedIn] = useState(false);
  useEffect(() => {
    setLoggedIn(!!getToken());
  }, []);
  return loggedIn;
}

export function AuthLink({ className }: { className: string }) {
  const loggedIn = useLoggedIn();
  return loggedIn ? (
    <Link className={className} href="/dashboard">
      Open dashboard
    </Link>
  ) : (
    <Link className={className} href="/login">
      Log in
    </Link>
  );
}

/** Open sign-up: /register offers "Continue with Google" (and, behind an
 * invite link, a username and password). */
export function SignUpLink({ className = "nb-btn nb-btn--solid", label = "Create an account" }: { className?: string; label?: string }) {
  return (
    <Link className={className} href="/register" data-magnetic>
      <span className="nb-btn-label">{label}</span>
      <svg className="nb-btn-arrow" viewBox="0 0 16 16" aria-hidden="true">
        <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </Link>
  );
}

export function RequestAccess({ className = "nb-btn nb-btn--solid", label = "Request access" }: { className?: string; label?: string }) {
  return (
    <a className={className} href={REQUEST_ACCESS} data-magnetic>
      <span className="nb-btn-label">{label}</span>
      <svg className="nb-btn-arrow" viewBox="0 0 16 16" aria-hidden="true">
        <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </a>
  );
}
