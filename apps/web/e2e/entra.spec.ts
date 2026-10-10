import { expect, test } from "@playwright/test";

// Optional Microsoft Entra ID SSO, without a real tenant: /auth/config is switched to SSO and the tenant's metadata is
// served locally. Checks that the web app starts an authorization-code + PKCE sign-in for the API scope, and that
// email + password stays available next to it unless the API turns passwords off.
const TENANT = "11111111-1111-1111-1111-111111111111";
const SPA = "33333333-3333-3333-3333-333333333333";
const SCOPE = "api://22222222-2222-2222-2222-222222222222/access_as_user";
const AUTHORITY = `https://login.microsoftonline.com/${TENANT}`;
const SSO = { provider: "entra", client_id: SPA, authority: AUTHORITY, scopes: [SCOPE] };

test("SSO only: 'Sign in with Microsoft' starts an auth-code + PKCE sign-in for the API scope", async ({ page }) => {
  await page.route("**/auth/config", (route) => route.fulfill({ json: { password: false, sso: SSO, dev_sign_in: false } }));
  await page.route(`${AUTHORITY}/v2.0/.well-known/openid-configuration`, (route) => route.fulfill({ json: {
    issuer: `${AUTHORITY}/v2.0`, authorization_endpoint: `${AUTHORITY}/oauth2/v2.0/authorize`,
    token_endpoint: `${AUTHORITY}/oauth2/v2.0/token`, end_session_endpoint: `${AUTHORITY}/oauth2/v2.0/logout`,
    jwks_uri: `${AUTHORITY}/discovery/v2.0/keys`, response_modes_supported: ["query", "fragment", "form_post"],
  } }));
  let authorize: URL | null = null;
  await page.route(`${AUTHORITY}/oauth2/v2.0/authorize**`, (route) => {
    authorize = new URL(route.request().url());
    return route.fulfill({ contentType: "text/html", body: "<p>Microsoft sign-in</p>" });
  });

  await page.goto("/");
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page.getByLabel("Password")).toHaveCount(0);
  await expect(page.getByText("Development: sign in as")).toHaveCount(0);
  await page.getByRole("button", { name: "Sign in with Microsoft" }).click();
  await expect(page.getByText("Microsoft sign-in")).toBeVisible();

  const params = authorize!.searchParams;
  expect(params.get("client_id")).toBe(SPA);
  expect(params.get("response_type")).toBe("code");
  expect(params.get("code_challenge_method")).toBe("S256");
  expect(params.get("code_challenge")).toBeTruthy();
  expect(params.get("scope")!.split(" ")).toContain(SCOPE);
  expect(params.get("redirect_uri")).toBe("http://localhost:5199/");
});

test("Passwords and SSO: both ways to sign in are offered", async ({ page }) => {
  await page.route("**/auth/config", (route) => route.fulfill({ json: { password: true, sso: SSO, dev_sign_in: false } }));
  await page.route(`${AUTHORITY}/**`, (route) => route.abort());
  await page.goto("/signin");
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in with Microsoft" })).toBeVisible();
});
