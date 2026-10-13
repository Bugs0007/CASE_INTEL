import { APIError } from "@/lib/api/client";

/** The Google OAuth web client id. Unset means Google sign-in is switched
 * off for this deployment: no button is rendered anywhere. */
export const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

export interface GoogleErrorMessage {
  message: string;
  /** The server says Google sign-in isn't configured: drop the button
   * instead of showing an error the user can't act on. */
  hideButton: boolean;
}

const MESSAGES: Record<string, string> = {
  invite_required: "Case Intel is invite-only right now. Ask for an invitation.",
  google_token_invalid: "Google sign-in didn't go through. Try again.",
  google_unavailable: "Couldn't reach Google just now. Try again in a moment.",
};

// Codes whose server `detail` is already written for the user.
const USE_SERVER_DETAIL = new Set([
  "account_exists",
  "account_disabled",
  "already_linked",
  "google_account_taken",
  "no_password",
  "has_password",
  "credentials_locked",
  "not_linked",
]);

/** Maps a failed /auth/google/* call to plain words for the user. */
export function googleErrorMessage(error: unknown): GoogleErrorMessage {
  if (error instanceof APIError) {
    const body = (error.data && typeof error.data === "object" ? error.data : {}) as Record<string, unknown>;
    const code = typeof body.code === "string" ? body.code : "";
    const detail = typeof body.detail === "string" ? body.detail : "";

    if (code === "google_not_configured") return { message: "", hideButton: true };
    if (USE_SERVER_DETAIL.has(code) && detail) return { message: detail, hideButton: false };
    if (MESSAGES[code]) return { message: MESSAGES[code], hideButton: false };
    if (detail) return { message: detail, hideButton: false };
    return { message: MESSAGES.google_token_invalid, hideButton: false };
  }
  return { message: "Could not reach the server. Please try again.", hideButton: false };
}
