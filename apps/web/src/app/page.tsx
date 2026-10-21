import Image from "next/image";
import { ApiStatus } from "@/shared/api-status";
import { Brand } from "@/shared/brand";
import { ThemeToggle } from "@/shared/theme";
import symbol from "@/shared/assets/ukladen-avatar.png";

export default function Home() {
  return (
    <main className="landing">
      <header className="landing-header">
        <Brand />
        <nav aria-label="Главная навигация">
          <ThemeToggle />
          <a href="/workspace">
            Войти <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </header>
      <section className="landing-hero" aria-labelledby="workspace-title">
        <div>
          <span className="eyebrow">МЕНЬШЕ ХАОСА. БОЛЬШЕ СВОЕГО.</span>
          <h1 id="workspace-title">
            Всё важное —<br />
            <span>в одном месте</span>
          </h1>
          <p>
            Расписание, личные планы и знания. Пространство, которое
            подстраивается под твою жизнь, а не наоборот.
          </p>
          <a className="primary-button" href="/workspace">
            Открыть календарь <span aria-hidden="true">→</span>
          </a>
        </div>
        <div className="landing-brand-art" aria-hidden="true">
          <Image src={symbol} alt="" width={320} height={320} priority />
        </div>
      </section>
      <section className="landing-features" aria-label="Возможности Ukladen">
        <article>
          <small>01 / ПЛАНИРУЙ</small>
          <h2>Неделя в своём ритме</h2>
          <p>
            Пары из IIS и личные события рядом. Учебная группа — по желанию.
          </p>
        </article>
        <article>
          <small>02 / СОХРАНЯЙ</small>
          <h2>Место для твоих мыслей</h2>
          <p>
            Вложенные страницы, списки и материалы. Связи между ними выбираешь
            ты.
          </p>
        </article>
        <article>
          <small>03 / ОРГАНИЗУЙ</small>
          <h2>Порядок без ограничений</h2>
          <p>
            Коллекции, теги и собственные базы. Без обязательных предметов и
            шаблонов.
          </p>
        </article>
      </section>
      <footer className="landing-footer">
        <p>Ukladen · Личное пространство для учёбы и жизни</p>
        <ApiStatus />
      </footer>
    </main>
  );
}
