"use client";

import Link from "next/link";
import { Brand } from "@/shared/brand";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import "../../workspace/workspace.css";
import "./reset-password.css";

type Mode = "loading" | "request" | "confirm" | "sent" | "success" | "invalid";
type Stage = "csrf" | "request" | "confirmation" | "network";

function logFailure(stage: Stage, response?: Response) {
  const requestId = response?.headers.get("x-request-id");
  console.warn(JSON.stringify({
    event: "web.password_reset_failed", stage, status_code: response?.status,
    request_id: requestId && /^[0-9a-f]{32}$/.test(requestId) ? requestId : undefined,
  }));
}

async function postReset(action: "request" | "confirm", body: Record<string, string>) {
  const options: RequestInit = { credentials: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer" };
  const csrf = await fetch("/api/v1/auth/csrf", options);
  if (!csrf.ok) return { response: csrf, stage: "csrf" as const };
  const data: { csrf_token?: unknown } = await csrf.json();
  if (typeof data.csrf_token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(data.csrf_token)) throw new Error("Invalid CSRF response.");
  const response = await fetch(`/api/v1/auth/password-reset/${action}`, {
    ...options, method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token },
    body: JSON.stringify(body),
  });
  return { response, stage: action === "request" ? "request" as const : "confirmation" as const };
}

export function ResetPassword() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("loading");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const token = useRef<string | null>(null);
  const initialization = useRef<Promise<string | null | undefined> | null>(null);

  useEffect(() => {
    // Capture once across effect replays; the secret stays in this mounted form only.
    initialization.current ??= Promise.resolve().then(() => {
      const { hash, search, pathname } = window.location;
      const tokens = new URLSearchParams(hash.slice(1)).getAll("token");
      window.history.replaceState(window.history.state, "", pathname);
      if (!hash && !search) return undefined;
      return !search && tokens.length === 1 && /^[A-Za-z0-9_-]{43}$/.test(tokens[0]) ? tokens[0] : null;
    });
    let mounted = true;
    void initialization.current.then(value => {
      if (!mounted) return;
      token.current = value ?? null;
      setMode(value === undefined ? "request" : value === null ? "invalid" : "confirm");
    });
    const openAnotherLink = () => window.location.reload();
    window.addEventListener("hashchange", openAnotherLink);
    return () => { mounted = false; window.removeEventListener("hashchange", openAnotherLink); };
  }, []);

  function clearSecret() {
    token.current = null;
    initialization.current = null;
    setPassword("");
    setConfirmation("");
  }

  function requestAnotherLink() {
    clearSecret();
    setMessage("");
    setMode("request");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    setMessage("");
    if (mode === "confirm" && password !== confirmation) { setMessage("Пароли не совпадают."); return; }
    if (mode === "confirm" && !token.current) { setMode("invalid"); return; }
    if (mode !== "request" && mode !== "confirm") return;
    inFlight.current = true;
    setBusy(true);
    try {
      const { response, stage } = mode === "request"
        ? await postReset("request", { email })
        : await postReset("confirm", { token: token.current!, new_password: password });
      if (stage === "request" && response.status === 202) { setMode("sent"); return; }
      if (stage === "confirmation" && response.status === 204) {
        clearSecret();
        setEmail("");
        queryClient.removeQueries({ queryKey: ["workspace-session"] });
        setMode("success");
        return;
      }
      if (stage === "confirmation" && response.status === 400) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        if (payload?.detail === "New password does not meet the password policy.") {
          setMessage("Новый пароль не соответствует требованиям сервиса. Попробуйте более длинный пароль.");
        } else { clearSecret(); setMode("invalid"); }
        return;
      }
      logFailure(stage, response);
      setMessage(response.status === 429 ? "Слишком много попыток. Попробуйте позже."
        : response.status === 403 ? "Не удалось подтвердить запрос. Повторите попытку."
        : "Сервис временно недоступен. Повторите попытку позже.");
    } catch {
      logFailure("network");
      setMessage("Не удалось выполнить запрос. Проверьте соединение и попробуйте снова.");
    } finally { inFlight.current = false; setBusy(false); }
  }

  return <main className="workspace-auth password-reset">
    <section className="auth-card password-reset-card" aria-labelledby="reset-title">
      <Brand />
      <h1 id="reset-title">{mode === "confirm" ? "Новый пароль" : mode === "success" ? "Пароль изменён" : "Восстановление пароля"}</h1>
      {mode === "loading" && <p role="status">Проверяем ссылку…</p>}
      {mode === "request" && <p className="auth-description">Укажите почту аккаунта — отправим ссылку для установки нового пароля.</p>}
      {mode === "confirm" && <p className="auth-description" id="password-help">Введите новый пароль дважды. Используйте не менее 12 символов.</p>}
      {(mode === "request" || mode === "confirm") && <form onSubmit={submit} aria-busy={busy}>
        {mode === "request" ? <>
          <label htmlFor="reset-email">Электронная почта</label>
          <input id="reset-email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} />
        </> : <>
          <label htmlFor="new-password">Новый пароль</label>
          <input id="new-password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} aria-describedby="password-help" value={password} onChange={event => setPassword(event.target.value)} />
          <label htmlFor="confirm-password">Повторите пароль</label>
          <input id="confirm-password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} value={confirmation} onChange={event => setConfirmation(event.target.value)} />
        </>}
        {message && <p className="form-error" role="alert">{message}</p>}
        <button className="primary-button auth-submit" disabled={busy}>{busy ? "Секунду…" : mode === "request" ? "Отправить ссылку" : "Сохранить пароль"}</button>
      </form>}
      {mode === "sent" && <>
        <p role="status">Если для этой почты есть подходящий аккаунт, мы отправили письмо со ссылкой. Проверьте входящие и папку «Спам».</p>
        <button className="primary-button auth-submit" onClick={requestAnotherLink}>Запросить ещё раз</button>
      </>}
      {mode === "invalid" && <>
        <p className="form-error" role="alert">Ссылка недействительна, уже использована или срок её действия истёк. Запросите новое письмо.</p>
        <button className="primary-button auth-submit" onClick={requestAnotherLink}>Запросить новую ссылку</button>
      </>}
      {mode === "success" && <p role="status">Пароль сохранён. Войдите с новым паролем. Предыдущие сессии аккаунта завершены.</p>}
      <Link className="auth-recovery" href="/workspace">Вернуться ко входу</Link>
    </section>
  </main>;
}
