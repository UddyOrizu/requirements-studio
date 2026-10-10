// Sign-in for the web app. Accounts are internal; people sign in with email + password (a session token from the
// API), or with Microsoft Entra ID when the API has SSO switched on (MSAL, authorization code + PKCE; the API maps
// the Microsoft account onto the internal one an admin added). GET /auth/config says which are offered.
import { InteractionRequiredAuthError, PublicClientApplication } from "@azure/msal-browser";

export type AuthConfig = {
  password: boolean;
  sso: { provider: "entra"; client_id: string; authority: string; scopes: string[] } | null;
  dev_sign_in: boolean;
};
export type SessionUser = { user_id: string; name: string; email: string; role: "user" | "admin" };

const TOKEN = "rs.token"; // our session token (password or dev sign-in)
let config: AuthConfig | null = null;
let msal: PublicClientApplication | null = null;

export async function initAuth(): Promise<AuthConfig> {
  if (config) return config;
  const res = await fetch("/auth/config");
  config = (await res.json()) as AuthConfig;
  if (config.sso) {
    msal = new PublicClientApplication({
      auth: { clientId: config.sso.client_id, authority: config.sso.authority, redirectUri: `${window.location.origin}/` },
      cache: { cacheLocation: "sessionStorage" },
    });
    await msal.initialize();
    const result = await msal.handleRedirectPromise(); // back from the Microsoft sign-in page
    if (result?.account) msal.setActiveAccount(result.account);
    else if (!msal.getActiveAccount() && msal.getAllAccounts().length) msal.setActiveAccount(msal.getAllAccounts()[0]);
  }
  return config;
}

export function authConfig(): AuthConfig | null {
  return config;
}

export function isSignedIn(): boolean {
  return Boolean(localStorage.getItem(TOKEN)) || Boolean(msal?.getActiveAccount());
}

/** A bearer token for the API: our session token, else a Microsoft access token (refreshed silently). */
export async function accessToken(): Promise<string | null> {
  const local = localStorage.getItem(TOKEN);
  if (local) return local;
  const active = msal?.getActiveAccount();
  if (!msal || !active || !config?.sso) return null;
  try {
    return (await msal.acquireTokenSilent({ scopes: config.sso.scopes, account: active })).accessToken;
  } catch (e) {
    if (e instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect({ scopes: config.sso.scopes, account: active });
      return null;
    }
    throw e;
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = data.errors?.[0]?.message ?? data.title ?? data.detail ?? `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : "Request failed");
  }
  return data as T;
}

export async function signInWithPassword(email: string, password: string): Promise<SessionUser> {
  const r = await post<{ access_token: string; user: SessionUser }>("/auth/login", { email, password });
  localStorage.setItem(TOKEN, r.access_token);
  return r.user;
}

/** Invitation or reset link → choose a password; signs in. */
export async function setPassword(token: string, password: string): Promise<SessionUser> {
  const r = await post<{ access_token: string; user: SessionUser }>("/auth/password/set", { token, password });
  localStorage.setItem(TOKEN, r.access_token);
  return r.user;
}

export async function forgotPassword(email: string): Promise<void> {
  await post("/auth/password/forgot", { email });
}

/** After a password change the API signs out other sessions and hands this one a fresh token. */
export function replaceToken(token: string): void {
  localStorage.setItem(TOKEN, token);
}

export async function signInWithMicrosoft(): Promise<void> {
  if (!msal || !config?.sso) throw new Error("Microsoft sign-in is not configured");
  await msal.loginRedirect({ scopes: config.sso.scopes, prompt: "select_account" });
}

/** Development only (RS_ENV=dev|test): sign in as any active user. */
export async function signInAs(userId: string): Promise<void> {
  const res = await fetch("/dev/token", { method: "POST", body: new URLSearchParams({ username: userId }) });
  if (!res.ok) throw new Error("Sign-in failed");
  localStorage.setItem(TOKEN, (await res.json()).access_token);
}

export async function signOut(): Promise<void> {
  localStorage.removeItem(TOKEN);
  if (msal?.getActiveAccount()) {
    await msal.logoutRedirect({ postLogoutRedirectUri: `${window.location.origin}/signin` });
    return;
  }
  window.location.assign("/signin");
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN);
}
