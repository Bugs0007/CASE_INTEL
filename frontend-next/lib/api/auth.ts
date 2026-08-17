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

export interface ChangePasswordResponse {
  token: string;
}

/** Self-service password change. On success the server rotates the auth
 * token (every existing token for this user is deleted, a fresh one
 * issued) -- the caller must store the returned token in place of the
 * old one, or the current session stops authenticating on its very next
 * request. Same credentials_locked 403 as changeUsername(). */
export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<ChangePasswordResponse> {
  return apiClient<ChangePasswordResponse>("/auth/change-password/", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
