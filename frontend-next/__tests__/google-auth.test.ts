import { describe, it, expect } from "vitest";
import { APIError } from "@/lib/api/client";
import { googleErrorMessage } from "@/lib/google-auth";

const fail = (status: number, body: unknown) => new APIError(status, body);

describe("googleErrorMessage", () => {
  it("shows the server's own text for account_exists", () => {
    const detail =
      "An account with this email already exists. Sign in with your username and password, then connect Google from Settings.";
    expect(googleErrorMessage(fail(409, { code: "account_exists", detail }))).toEqual({
      message: detail,
      hideButton: false,
    });
  });

  it("explains invite-only sign-up", () => {
    expect(googleErrorMessage(fail(403, { code: "invite_required" }))).toEqual({
      message: "Case Intel is invite-only right now. Ask for an invitation.",
      hideButton: false,
    });
  });

  it("asks to try again when the Google token was rejected", () => {
    expect(googleErrorMessage(fail(401, { code: "google_token_invalid" }))).toEqual({
      message: "Google sign-in didn't go through. Try again.",
      hideButton: false,
    });
  });

  it("hides the button when Google sign-in isn't configured", () => {
    expect(googleErrorMessage(fail(503, { code: "google_not_configured" }))).toEqual({
      message: "",
      hideButton: true,
    });
  });

  it("passes through server text for link/unlink conflicts", () => {
    const detail = "That Google account is connected to a different Case Intel account.";
    expect(googleErrorMessage(fail(409, { code: "google_account_taken", detail })).message).toBe(detail);
  });

  it("falls back for unknown API errors and for network failures", () => {
    expect(googleErrorMessage(fail(500, null)).message).toBe("Google sign-in didn't go through. Try again.");
    expect(googleErrorMessage(new TypeError("Failed to fetch"))).toEqual({
      message: "Could not reach the server. Please try again.",
      hideButton: false,
    });
  });
});
