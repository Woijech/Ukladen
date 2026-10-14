import type { Metadata } from "next";
import { Workspace } from "./workspace";

export const metadata: Metadata = {
  title: "Пространство — Ukladen",
  description: "Личное расписание и планы в Ukladen.",
};

export default function WorkspacePage() {
  return <Workspace />;
}
