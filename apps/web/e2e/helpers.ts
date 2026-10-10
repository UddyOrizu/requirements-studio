import { type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://localhost:8799";
export const DEV_PASSWORD = "requirements-studio-dev"; // the seeded dev users (services/identity_audit/dev.py)

export async function seed(request: APIRequestContext, scenario: "samples" | "kyc_before_refinement") {
  const res = await request.post(`${API}/dev/seed`, { data: { scenario } });
  if (!res.ok()) throw new Error(`seed failed: ${res.status()} ${await res.text()}`);
}

export async function token(request: APIRequestContext, user: string): Promise<string> {
  const res = await request.post(`${API}/dev/token`, { form: { username: user } });
  if (!res.ok()) throw new Error(`dev token failed: ${res.status()} ${await res.text()}`);
  return (await res.json()).access_token;
}

/** Signed in as `user` for every page load of this test. */
export async function signIn(page: Page, request: APIRequestContext, user = "user_sarah_lin") {
  const t = await token(request, user);
  await page.addInitScript((value) => localStorage.setItem("rs.token", value), t);
}

/** Switch the signed-in user mid-test (signIn's init script would put the first user back on every load). */
export async function switchUser(page: Page, request: APIRequestContext, user: string) {
  const t = await token(request, user);
  await page.goto("/signin");
  await page.evaluate((value) => localStorage.setItem("rs.token", value), t);
}

export async function lastEmail(request: APIRequestContext, to: string): Promise<{ subject: string; text: string }> {
  const res = await request.get(`${API}/dev/emails`, { params: { to } });
  const emails = await res.json();
  if (!emails.length) throw new Error(`no email to ${to}`);
  return emails[0];
}
