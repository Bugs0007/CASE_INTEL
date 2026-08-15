import { apiClient } from "./client";

export interface AuthResponse {
  token: string;
  user_id: number;
  username: string;
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return apiClient<AuthResponse>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return apiClient<void>("/auth/logout/", { method: "POST" });
}
