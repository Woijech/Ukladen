import { ApiStatus } from "@/shared/api-status";

export default function Home() {
  return (
    <main>
      <header><span className="brand">Ukladen</span></header>
      <section aria-labelledby="workspace-title">
        <p className="eyebrow">Ваше пространство для учёбы</p>
        <h1 id="workspace-title">Всё важное — в одном месте</h1>
        <p>Расписание учёбы и личные планы в одном календаре.</p>
        <p><a href="/workspace">Открыть календарь</a></p>
        <ApiStatus />
      </section>
    </main>
  );
}
