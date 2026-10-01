import { ApiStatus } from "@/shared/api-status";

export default function Home() {
  return (
    <main>
      <header><span className="brand">BSUIR Student Workspace</span></header>
      <section aria-labelledby="workspace-title">
        <p className="eyebrow">Ваше пространство для учёбы</p>
        <h1 id="workspace-title">Всё важное — в одном месте</h1>
        <p>Расписание, личные планы и учебные материалы. Пространство готовится к запуску.</p>
        <ApiStatus />
      </section>
    </main>
  );
}
