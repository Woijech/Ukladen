import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace } from "./workspace-fixtures";

const destination = "https://accounts.google.com/o/oauth2/v2/auth?state=private-test-state";
const csrf = "c".repeat(43);
const password = "private-current-password";

async function signedOut(page: Page) {
  await page.route("**/api/v1/users/me", route => route.fulfill({ status: 401 }));
}

async function googlePage(page: Page) {
  await page.route("https://accounts.google.com/**", route => route.fulfill({
    contentType: "text/html", body: "<h1>Google account chooser</h1>",
  }));
}

async function openLink(page: Page) {
  await page.getByRole("button", { name: "Меню профиля" }).last().click();
  await page.getByRole("button", { name: "Связать с Google", exact: true }).click();
  return page.getByRole("dialog", { name: "Связать аккаунт с Google" });
}

for (const register of [false, true]) {
  test(`Google ${register ? "registration" : "login"} starts once without submitting password fields`, async ({ page, context }) => {
    await signedOut(page);
    await googlePage(page);
    let starts = 0;
    await page.route("**/api/v1/auth/google/start", async route => {
      starts++;
      expect(route.request().method()).toBe("GET");
      expect(route.request().headers().accept).toBe("application/json");
      expect(route.request().headers().referer).toBeUndefined();
      expect(route.request().postData()).toBeNull();
      await route.fulfill({ json: { authorization_url: destination },
        headers: { "Set-Cookie": "ukladen_oauth=browser-binding; Path=/; HttpOnly; SameSite=Lax" } });
    });
    await page.goto("/workspace");
    if (register) await page.getByRole("button", { name: "Создать аккаунт", exact: true }).click();
    const button = page.getByRole("button", { name: "Продолжить с Google" });
    await button.evaluate((element: HTMLButtonElement) => { element.click(); element.click(); });
    await expect(page).toHaveURL(destination);
    expect(starts).toBe(1);
    const cookie = (await context.cookies("http://127.0.0.1:3001")).find(cookie => cookie.name === "ukladen_oauth");
    expect(cookie).toMatchObject({ httpOnly: true, sameSite: "Lax" });
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
    await page.goBack();
    await expect(page.getByRole("button", { name: "Продолжить с Google" })).toBeEnabled();
  });
}

for (const status of [403, 429, 503]) {
  test(`Google start ${status} stays on sign-in and can retry without exposing provider details`, async ({ page }) => {
    await signedOut(page);
    await googlePage(page);
    const diagnostics: string[] = [];
    page.on("console", message => { if (message.text().startsWith('{"event":"web.')) diagnostics.push(message.text()); });
    let attempts = 0;
    await page.route("**/api/v1/auth/google/start", async route => {
      attempts++;
      await route.fulfill(attempts === 1
        ? { status, json: { detail: `secret ${password} ${destination}` }, headers: { "X-Request-ID": "a".repeat(32) } }
        : { json: { authorization_url: destination } });
    });
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Продолжить с Google" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(status === 429 ? "Слишком много попыток" : status === 403 ? "Не удалось подтвердить запрос" : "временно недоступен");
    await expect(page).toHaveURL("/workspace");
    expect(diagnostics.map(entry => JSON.parse(entry))).toContainEqual({
      event: "web.google_auth_failed", stage: "login", status_code: status, request_id: "a".repeat(32),
    });
    expect(diagnostics.join("\n")).not.toContain(password);
    expect(diagnostics.join("\n")).not.toContain(destination);
    await page.getByRole("button", { name: "Продолжить с Google" }).click();
    await expect(page).toHaveURL(destination);
    expect(attempts).toBe(2);
  });
}

for (const url of ["https://evil.example/signin", "javascript:alert(1)", "https://accounts.google.com.evil.example/o/oauth2/v2/auth", null]) {
  test(`Google start refuses malformed or untrusted destination ${url}`, async ({ page }) => {
    await signedOut(page);
    await page.route("**/api/v1/auth/google/start", route => route.fulfill({ json: { authorization_url: url } }));
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Продолжить с Google" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Не удалось открыть Google");
    await expect(page).toHaveURL("/workspace");
    await expect(page.getByRole("button", { name: "Продолжить с Google" })).toBeEnabled();
  });
}

test("Google network failure permits retry without replacing password sign-in", async ({ page }) => {
  await signedOut(page);
  await page.route("**/api/v1/auth/google/start", route => route.abort());
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Продолжить с Google" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Проверьте соединение");
  await expect(page.getByRole("button", { name: "Войти", exact: true })).toBeEnabled();
});

for (const mobile of [false, true]) {
  test(`Google linking from ${mobile ? "mobile" : "desktop"} profile requires password and CSRF`, async ({ page }) => {
    await mockWorkspace(page);
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await googlePage(page);
    await page.route("**/api/v1/auth/csrf", route => route.fulfill({ json: { csrf_token: csrf },
      headers: { "Set-Cookie": `ukladen_csrf=${csrf}; Path=/; HttpOnly; SameSite=Lax` } }));
    let links = 0;
    await page.route("**/api/v1/auth/google/link/start", async route => {
      links++;
      const request = route.request();
      expect(request.method()).toBe("POST");
      expect(request.headers().accept).toBe("application/json");
      expect(request.headers()["x-csrf-token"]).toBe(csrf);
      expect(request.headers().cookie).toContain(`ukladen_csrf=${csrf}`);
      expect(request.headers().origin).toBe("http://127.0.0.1:3001");
      expect(request.headers().referer).toBeUndefined();
      expect(request.postDataJSON()).toEqual({ current_password: password });
      await route.fulfill({ json: { authorization_url: destination } });
    });
    await page.goto("/workspace");
    const dialog = await openLink(page);
    await dialog.getByRole("button", { name: "Продолжить с Google" }).click();
    expect(links).toBe(0);
    await dialog.getByLabel("Текущий пароль Ukladen").fill(password);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await openLink(page);
    await expect(dialog.getByLabel("Текущий пароль Ukladen")).toHaveValue("");
    await dialog.getByLabel("Текущий пароль Ukladen").fill(password);
    await dialog.getByRole("button", { name: "Продолжить с Google" }).click();
    await expect(page).toHaveURL(destination);
    expect(links).toBe(1);
  });
}

test("link errors preserve the current session, permit correction and never log the password", async ({ page }) => {
  await mockWorkspace(page);
  await googlePage(page);
  const diagnostics: string[] = [];
  page.on("console", message => { if (message.text().startsWith('{"event":"web.')) diagnostics.push(message.text()); });
  await page.route("**/api/v1/auth/csrf", route => route.fulfill({ json: { csrf_token: csrf } }));
  let links = 0;
  await page.route("**/api/v1/auth/google/link/start", async route => {
    links++;
    await route.fulfill(links === 1 ? { status: 401, json: { detail: "Invalid current password.", private: password } } : { json: { authorization_url: destination } });
  });
  await page.goto("/workspace");
  const dialog = await openLink(page);
  await dialog.getByLabel("Текущий пароль Ukladen").fill("wrong-password");
  await dialog.getByRole("button", { name: "Продолжить с Google" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Проверьте текущий пароль");
  await expect(page).toHaveURL("/workspace");
  expect(diagnostics.join("\n")).not.toContain(password);
  expect(diagnostics.join("\n")).not.toContain("wrong-password");
  await dialog.getByLabel("Текущий пароль Ukladen").fill(password);
  await dialog.getByRole("button", { name: "Продолжить с Google" }).click();
  await expect(page).toHaveURL(destination);
  expect(links).toBe(2);
});

test("invalid CSRF cannot initiate linking and a closed dialog discards the password", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/auth/csrf", route => route.fulfill({ json: { csrf_token: "invalid" } }));
  let links = 0;
  await page.route("**/api/v1/auth/google/link/start", route => { links++; return route.fulfill({ status: 500 }); });
  await page.goto("/workspace");
  const dialog = await openLink(page);
  await dialog.getByLabel("Текущий пароль Ukladen").fill(password);
  await dialog.getByRole("button", { name: "Продолжить с Google" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Не удалось открыть Google");
  expect(links).toBe(0);
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await openLink(page);
  await expect(dialog.getByLabel("Текущий пароль Ukladen")).toHaveValue("");
});

for (const throughRequest of [false, true]) {
  test(`session expiry ${throughRequest ? "during linking" : "during revalidation"} discards the Google password dialog`, async ({ page }) => {
    const state = await mockWorkspace(page);
    await page.route("**/api/v1/auth/csrf", route => route.fulfill({ json: { csrf_token: csrf } }));
    await page.route("**/api/v1/auth/google/link/start", async route => {
      state.authenticated = false;
      await route.fulfill({ status: 401, json: { detail: "Invalid or expired session." } });
    });
    await page.goto("/workspace");
    const dialog = await openLink(page);
    await dialog.getByLabel("Текущий пароль Ukladen").fill(password);
    if (throughRequest) await dialog.getByRole("button", { name: "Продолжить с Google" }).click();
    else {
      state.authenticated = false;
      await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
    }
    await expect(page.getByRole("heading", { name: "Войти в Ukladen" })).toBeVisible();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator("#google-link-password")).toHaveCount(0);
  });
}

test("callback error page is private, explains existing-account linking and allows a new start", async ({ page, request }) => {
  await googlePage(page);
  await page.route("**/api/v1/auth/google/start", route => route.fulfill({ json: { authorization_url: destination } }));
  const response = await request.get("/auth/error");
  expect(response.status()).toBe(200);
  expect(response.headers()["referrer-policy"]).toBe("no-referrer");
  expect(response.headers()["cache-control"]).toContain("no-store");
  expect(response.headers()["x-robots-tag"]).toContain("noindex");
  await page.goto("/auth/error");
  await expect(page.getByRole("heading", { name: "Не удалось войти через Google" })).toBeVisible();
  await expect(page.getByText(/Если вы уже регистрировались/)).toContainText("Связать с Google");
  await page.getByRole("button", { name: "Продолжить с Google" }).click();
  await expect(page).toHaveURL(destination);
});
