import Link from "next/link";
import { Brand } from "@/shared/brand";
import { ThemeToggle } from "@/shared/theme";

export default function NotFound() {
  return <main className="status-page">
    <header><Brand /><ThemeToggle /></header>
    <section>
      <p className="status-code">404</p>
      <h1>Этой страницы нет</h1>
      <p>Возможно, адрес изменился или в ссылке есть опечатка. Вернись в своё пространство, чтобы продолжить работу.</p>
      <Link className="primary-button" href="/workspace">Открыть пространство</Link>
    </section>
  </main>;
}
