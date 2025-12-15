import type { ReactNode } from "react";
import PageShell from "./components/layout/PageShell";
import "./globals.css";
import { WebSocketProvider } from "./providers/WebSocketProvider";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <WebSocketProvider>
        <PageShell>{children}</PageShell>
        </WebSocketProvider>
      </body>
    </html>
  );
}
