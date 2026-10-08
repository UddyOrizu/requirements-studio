import { type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://localhost:8799";

export async function seed(request: APIRequestContext, scenario: "samples" | "kyc_before_refinement") {
  const res = await request.post(`${API}/dev/seed`, { data: { scenario } });
  if (!res.ok()) throw new Error(`seed failed: ${res.status()} ${await res.text()}`);
}

export async function signIn(page: Page, request: APIRequestContext, user = "user_sarah_lin") {
  const res = await request.post(`${API}/dev/oidc/token`, { form: { username: user, password: "x" } });
  const { access_token } = await res.json();
  await page.addInitScript((t) => localStorage.setItem("rs.token", t), access_token);
}
