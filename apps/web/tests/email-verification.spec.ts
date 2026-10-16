import { test, expect } from "@playwright/test";

const token = "v".repeat(43);
const csrf = "c".repeat(43);
const path = "/auth/verify-email";

for (const scenario of [
  { code: 204, text: "Почта подтверждена." },
  { code: 400, text: "Ссылка недействительна" },
  { code: 401, text: "Откройте письмо в браузере регистрации" },
  { code: 429, text: "Слишком много попыток" },
  { code: 503, text: "Не удалось подтвердить почту" },
]) {
  test(`verification submits one CSRF-protected POST and handles ${scenario.code}`, async ({ page }) => {
    const diagnostics: string[] = [];
    page.on("console", message => {
      if (message.text().startsWith('{"event":"web.')) diagnostics.push(message.text());
    });
    let confirmations = 0;
    await page.route("**/api/v1/auth/csrf", async route => {
      expect(route.request().method()).toBe("GET");
      await route.fulfill({
        headers: { "Set-Cookie": `ukladen_csrf=${csrf}; Path=/; HttpOnly; SameSite=Lax` },
        json: { csrf_token: csrf },
      });
    });
    await page.route("**/api/v1/auth/email-verification/confirm", async route => {
      confirmations++;
      const request = route.request();
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({ token });
      expect(request.headers()["x-csrf-token"]).toBe(csrf);
      expect(request.headers().cookie).toContain(`ukladen_csrf=${csrf}`);
      expect(request.headers().origin).toBe("http://127.0.0.1:3001");
      expect(request.headers().referer).toBeUndefined();
      expect(request.url()).not.toContain(token);
      await route.fulfill({ status: scenario.code, body: "", headers: { "X-Request-ID": "a".repeat(32) } });
    });
    await page.goto(`${path}#token=${token}`);
    await expect(page.getByRole("status")).toContainText(scenario.text);
    await expect(page).toHaveURL(path);
    if (scenario.code === 401) {
      await expect(page.getByRole("link", { name: "Восстановить доступ по почте" })).toHaveAttribute("href", "/auth/reset-password");
      await expect(page.getByRole("link", { name: "Войти в Ukladen" })).toHaveAttribute("href", "/workspace");
    }
    expect(confirmations).toBe(1);
    expect(await page.evaluate(() => window.localStorage.length + window.sessionStorage.length)).toBe(0);
    if (scenario.code === 429 || scenario.code === 503) {
      expect(diagnostics.map(entry => JSON.parse(entry))).toContainEqual({
        event: "web.email_verification_failed", stage: "confirmation",
        status_code: scenario.code, request_id: "a".repeat(32),
      });
    }
    expect(diagnostics.join("\n")).not.toContain(token);
    expect(diagnostics.join("\n")).not.toContain(csrf);
  });
}

for (const suffix of ["", "#token=invalid", `#token=${token}&token=${token}`]) {
  test(`invalid verification fragment ${suffix || "missing"} never calls the API`, async ({ page }) => {
    const requests: string[] = [];
    await page.route("**/api/v1/auth/**", async route => {
      requests.push(route.request().url());
      await route.fulfill({ status: 500 });
    });
    await page.goto(path + suffix);
    await expect(page.getByRole("status")).toContainText("Ссылка недействительна");
    await expect(page).toHaveURL(path);
    expect(requests).toEqual([]);
  });
}

test("CSRF and network failures never submit confirmation or expose the token", async ({ page }) => {
  let confirmations = 0;
  await page.route("**/api/v1/auth/csrf", route => route.fulfill({ json: { csrf_token: "invalid" } }));
  await page.route("**/api/v1/auth/email-verification/confirm", async route => {
    confirmations++;
    await route.fulfill({ status: 204 });
  });
  await page.goto(`${path}#token=${token}`);
  await expect(page.getByRole("status")).toContainText("Не удалось подтвердить почту");
  expect(confirmations).toBe(0);
  await page.route("**/api/v1/auth/csrf", route => route.abort());
  await page.goto(`${path}#token=${token}`);
  await expect(page.getByRole("status")).toContainText("Не удалось подтвердить почту");
  await expect(page).toHaveURL(path);
  expect(confirmations).toBe(0);
});

test("plain GET preview cannot confirm email and the page has privacy headers", async ({ request }) => {
  const response = await request.get(`${path}#token=${token}`);
  expect(response.status()).toBe(200);
  expect(response.headers()["referrer-policy"]).toBe("no-referrer");
  expect(response.headers()["cache-control"]).toContain("no-store");
  expect(response.headers()["x-robots-tag"]).toContain("noindex");
  expect(await response.text()).not.toContain(token);
});
