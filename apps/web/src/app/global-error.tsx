"use client";

import ApplicationError from "./error";
import "./globals.css";

export default function GlobalError(props: Parameters<typeof ApplicationError>[0]) {
  return <html lang="ru"><body><ApplicationError {...props} /></body></html>;
}
