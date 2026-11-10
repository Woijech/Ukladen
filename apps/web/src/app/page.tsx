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
            Войти
          </a>
        </nav>
      </header>
      <section className="landing-hero" aria-labelledby="workspace-title">
        <div>
          <span className="eyebrow">Личное пространство для учёбы и жизни</span>
          <h1 id="workspace-title">
            У каждого плана<br />
            <span>своё место.</span>
          </h1>
          <p>
            Держи перед глазами свою неделю, собирай заметки
            и превращай большие планы в понятные задачи.
          </p>
          <a className="primary-button" href="/workspace">
            Открыть календарь
          </a>
        </div>
        <div className="landing-brand-art" aria-hidden="true">
          <Image src={symbol} alt="" width={320} height={320} priority />
        </div>
      </section>
      <section className="landing-features" aria-label="Возможности Ukladen">
        <article>
          <small>Календарь</small>
          <h2>Неделя в своём ритме</h2>
          <p>
            Пары из IIS и личные события рядом. Учебная группа по желанию.
          </p>
        </article>
        <article>
          <small>Заметки</small>
          <h2>Место для твоих мыслей</h2>
          <p>
            Вложенные страницы, списки и материалы. Связи между ними выбираешь
            ты.
          </p>
        </article>
        <article>
          <small>Организация</small>
          <h2>Свои связи и порядок</h2>
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
