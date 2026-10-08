// Thin client for /api/v1. Errors are RFC 7807 problems; ApiError keeps the body so screens can explain them.

const TOKEN_KEY = "rs.token";

export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(problemText(body) ?? `Request failed (${status})`);
  }
}

function problemText(body: any): string | undefined {
  if (!body) return undefined;
  if (Array.isArray(body.errors) && body.errors.length) return body.errors.map((e: any) => e.message).join(" ");
  if (typeof body.detail === "string") return body.detail;
  if (body.detail?.title) return body.detail.title;
  return body.title;
}

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401) {
    token.clear();
    window.location.assign("/signin");
  }
  if (!res.ok) {
    let problem: any;
    try { problem = await res.json(); } catch { problem = undefined; }
    throw new ApiError(res.status, problem);
  }
  return (raw ? res.text() : res.json()) as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  text: (path: string) => request<string>("GET", path, undefined, true),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
};

export async function signIn(username: string): Promise<void> {
  const form = new URLSearchParams({ username, password: "dev", grant_type: "password" });
  const res = await fetch("/dev/oidc/token", { method: "POST", body: form });
  if (!res.ok) throw new Error("Sign-in failed");
  token.set((await res.json()).access_token);
}

export function downloadUrl(path: string): string {
  return `/api/v1${path}`;
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${token.get()}` } });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
