// Thin client for /api/v1. Errors are RFC 7807 problems; ApiError keeps the body so screens can explain them.
import { accessToken, clearSession } from "./auth";

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

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const headers: Record<string, string> = {};
  const t = await accessToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401) {
    clearSession(); // expired, signed out elsewhere, or disabled
    window.location.assign(`/signin?next=${encodeURIComponent(window.location.pathname)}`);
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
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
};

export function downloadUrl(path: string): string {
  return `/api/v1${path}`;
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${await accessToken()}` } });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
