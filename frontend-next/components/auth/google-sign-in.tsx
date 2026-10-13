"use client";

import { useEffect, useRef, useState } from "react";
import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";
import { GOOGLE_CLIENT_ID } from "@/lib/google-auth";

interface GoogleSignInButtonProps {
  /** Called with Google's ID token ("credential") after the popup succeeds. */
  onCredential: (credential: string) => void;
  /** Google's own popup failed or was closed. */
  onError?: () => void;
  text?: "continue_with" | "signin_with" | "signup_with";
}

/** Google's rendered button (Identity Services), not a custom-drawn logo, so
 * the branding rules are Google's to enforce. Renders nothing when
 * NEXT_PUBLIC_GOOGLE_CLIENT_ID isn't set. */
export function GoogleSignInButton({ onCredential, onError, text = "continue_with" }: GoogleSignInButtonProps) {
  const holder = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | undefined>(undefined);

  // The button takes a pixel width (max 400); fit it to the card.
  useEffect(() => {
    const node = holder.current;
    if (!node) return;
    setWidth(Math.max(200, Math.min(400, Math.floor(node.clientWidth))));
  }, []);

  if (!GOOGLE_CLIENT_ID) return null;

  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <div ref={holder} className="flex w-full justify-center" data-testid="google-sign-in">
        <GoogleLogin
          theme="outline"
          text={text}
          shape="rectangular"
          width={width}
          onSuccess={(response) => {
            if (response.credential) onCredential(response.credential);
            else onError?.();
          }}
          onError={() => onError?.()}
        />
      </div>
    </GoogleOAuthProvider>
  );
}

export function OrDivider() {
  return (
    <div className="my-5 flex items-center gap-3 text-xs uppercase tracking-wider text-gray-400" aria-hidden="true">
      <span className="h-px flex-1 bg-gray-200" />
      or
      <span className="h-px flex-1 bg-gray-200" />
    </div>
  );
}
