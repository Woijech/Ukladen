"use client";

import { useQuery } from "@tanstack/react-query";

export function ApiStatus() {
  const { isPending, isError } = useQuery({
    queryKey: ["api-health"],
    queryFn: async () => {
      const response = await fetch("/api/health/live");
      if (!response.ok) throw new Error("API unavailable");
      const data: { status?: string } = await response.json();
      if (data.status !== "ok") throw new Error("Unexpected health response");
      return data;
    },
  });

  return <p role="status">{isPending ? "Проверка соединения…" : isError ? "Сервис временно недоступен" : "Соединение установлено"}</p>;
}
