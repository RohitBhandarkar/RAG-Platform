import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG Formulation Platform",
  description: "Formulation experiment reports and in-house experimentation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider
      appearance={{
        variables: { colorPrimary: "#2563eb", colorBackground: "#f8fafc" },
      }}
    >
      <html lang="en">
        <body className="min-h-screen bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
