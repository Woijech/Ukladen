"use client";

import { useEffect } from "react";
import { Brand } from "@/shared/brand";

export default function ApplicationError({ error, reset }: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Error messages/stacks and browser URLs may contain user data or verification tokens.
    console.error(JSON.stringify({
      event: "web.render_failed",
      digest: error.digest && /^[0-9]{1,20}$/.test(error.digest) ? error.digest : undefined,
    }));
  }, [error]);

  return (
    <main className="status-page">
      <header><Brand /></header>
      <section>
      <h1>Не удалось открыть страницу</h1>
      <p role="alert">Попробуйте ещё раз.</p>
      <div className="status-actions">
        <button className="primary-button" type="button" onClick={reset}>Повторить</button>
        <a className="secondary-button" href="/workspace">Открыть пространство</a>
      </div>
      </section>
    </main>
  );
}
