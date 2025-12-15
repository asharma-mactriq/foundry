// NO "use client"

import TopNav from "./TopNav";
import type { ReactNode } from "react";

export default function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-muted/30">
      {/* This is fine — TopNav itself is client */}
      <TopNav />
      <main className="pt-16 px-4">{children}</main>
    </div>
  );
}
