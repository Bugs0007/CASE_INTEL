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
