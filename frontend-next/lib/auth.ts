const TOKEN_KEY = "case_intel_token";
const USERNAME_KEY = "case_intel_username";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(USERNAME_KEY);
}

export function setUsername(username: string): void {
  window.localStorage.setItem(USERNAME_KEY, username);
}

export function clearUsername(): void {
  window.localStorage.removeItem(USERNAME_KEY);
}
