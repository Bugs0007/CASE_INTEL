import { apiClient } from "./client";

export interface AuthResponse {
  token: string;
  user_id: number;
  username: string;
}

export interface InviteValidation {
  valid: boolean;
  reason: "not_found" | "used" | "expired" | null;
  email: string | null;
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return apiClient<AuthResponse>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function validateInvite(token: string): Promise<InviteValidation> {
  return apiClient<InviteValidation>(`/auth/invite/${encodeURIComponent(token)}/`);
}

export function register(
  token: string,
  username: string,
  password: string,
  email?: string,
): Promise<AuthResponse> {
  return apiClient<AuthResponse>("/auth/register/", {
    method: "POST",
    body: JSON.stringify({ token, username, password, email: email || "" }),
  });
}

export function logout(): Promise<void> {
  return apiClient<void>("/auth/logout/", { method: "POST" });
}

export interface ChangeUsernameResponse {
  username: string;
}

/** Self-service username change -- rejected with a 403
 * ({ code: "credentials_locked" }) if an admin has locked this account
 * against changing its own credentials (see core/models/account_lock.py). */
export function changeUsername(
  currentPassword: string,
  newUsername: string,
): Promise<ChangeUsernameResponse> {
  return apiClient<ChangeUsernameResponse>("/auth/change-username/", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_username: newUsername }),
  });
}

/** One signed-in device (GET /api/auth/sessions/). */
export interface AuthSessionRow {
  id: number;
  source: string;
  source_display: string;
  user_agent: string;
  ip_address: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  /** The session this request came in on. */
  current: boolean;
}

export const authSessionsApi = {
  list: () => apiClient<AuthSessionRow[]>("/auth/sessions/"),
  revoke: (id: number) => apiClient<void>(`/auth/sessions/${id}/`, { method: "DELETE" }),
  revokeOthers: () =>
    apiClient<{ revoked: number }>("/auth/sessions/revoke-others/", { method: "POST" }),
};

export interface ChangePasswordResponse {
  token: string;
}

/** Self-service password change. On success the server ends every
 * session this account has (other devices included) and issues a fresh
 * one -- the caller must store the returned token in place of the old
 * one, or this device stops authenticating on its very next request. Same
 * credentials_locked 403 as changeUsername(). */
export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<ChangePasswordResponse> {
  return apiClient<ChangePasswordResponse>("/auth/change-password/", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
