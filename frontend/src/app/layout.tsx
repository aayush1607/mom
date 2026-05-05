import type { Metadata, Viewport } from "next";
import "./globals.css";

import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";

export const metadata: Metadata = {
  title: "mom.",
  description: "One nudge. One tap. Meals, handled.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "mom.",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#F4EBDB",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-IN">
      <body className="bg-bg text-ink min-h-screen antialiased">
        {children}
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
