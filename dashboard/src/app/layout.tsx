import type { Metadata } from "next";
import type { ReactNode } from "react";
import { TopBar } from "@/components/layout/top-bar";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "EvalOps",
  description:
    "Continuous evaluation and release gating for LLM, RAG, and agent systems.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>
          <div className="flex min-h-screen flex-col">
            <TopBar />
            <main className="flex-1">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
