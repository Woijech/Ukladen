"use client";

import Image from "next/image";
import { useEffect, useRef, useState, type FormEvent } from "react";
import google from "./assets/google-g.png";
import styles from "./google-auth.module.css";

export function GoogleAuth({ link = false, onSessionEnd }: { link?: boolean; onSessionEnd?: () => void }) {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) { inFlight.current = false; setBusy(false); }
    };
    window.addEventListener("pageshow", restore);
    return () => window.removeEventListener("pageshow", restore);
  }, []);

  async function start(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setMessage("");
    let navigating = false;
    let stage = link ? "link" : "login";
    const options: RequestInit = { credentials: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer", headers: { Accept: "application/json" } };
    try {
      let response: Response;
      if (link) {
        stage = "csrf";
        const csrf = await fetch("/api/v1/auth/csrf", options);
        if (!csrf.ok) response = csrf;
        else {
          const data: { csrf_token?: unknown } = await csrf.json();
          if (typeof data.csrf_token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(data.csrf_token)) throw new Error("Invalid CSRF response.");
          stage = "link";
          response = await fetch("/api/v1/auth/google/link/start", {
            ...options, method: "POST",
            headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token },
            body: JSON.stringify({ current_password: password }),
          });
        }
      } else response = await fetch("/api/v1/auth/google/start", options);
      if (!response.ok) {
        if (link && onSessionEnd && response.status === 401) {
          const failure = await response.json().catch(() => null) as { detail?: string } | null;
          if (failure?.detail !== "Invalid current password.") { setPassword(""); onSessionEnd(); return; }
        }
        const requestId = response.headers.get("x-request-id");
        console.warn(JSON.stringify({ event: "web.google_auth_failed", stage, status_code: response.status,
          request_id: requestId && /^[0-9a-f]{32}$/.test(requestId) ? requestId : undefined }));
        setMessage(response.status === 429 ? "Слишком много попыток. Попробуйте позже."
          : response.status === 401 ? "Проверьте текущий пароль. Для аккаунта без пароля привязка недоступна."
          : response.status === 403 ? "Не удалось подтвердить запрос. Обновите страницу и попробуйте снова."
          : "Вход через Google временно недоступен. Можно войти по почте и паролю.");
        return;
      }
      const payload: { authorization_url?: unknown } = await response.json();
      if (typeof payload.authorization_url !== "string") throw new Error("Invalid authorization response.");
      const url = new URL(payload.authorization_url);
      if (url.origin !== "https://accounts.google.com" || url.username || url.password || url.pathname !== "/o/oauth2/v2/auth") throw new Error("Invalid authorization destination.");
      setPassword("");
      window.location.assign(url.href);
      navigating = true;
    } catch {
      console.warn(JSON.stringify({ event: "web.google_auth_failed", stage: "network" }));
      setMessage("Не удалось открыть Google. Проверьте соединение и попробуйте снова.");
    } finally {
      if (!navigating) { inFlight.current = false; setBusy(false); }
    }
  }

  const button = <button className={styles.button} type={link ? "submit" : "button"} disabled={busy}
    onClick={link ? undefined : () => void start()}>
    <Image src={google} alt="" width={20} height={20} />
    <span>{busy ? "Открываем Google…" : "Продолжить с Google"}</span>
  </button>;
  const error = message && <p className={styles.error} role="alert">{message}</p>;

  return link ? <form onSubmit={start} aria-busy={busy}>
    <label htmlFor="google-link-password">Текущий пароль Ukladen</label>
    <input id="google-link-password" type="password" autoComplete="current-password" required maxLength={1024}
      value={password} onChange={event => setPassword(event.target.value)} />
    {button}{error}
  </form> : <div className={styles.login} aria-busy={busy}>{button}{error}</div>;
}
