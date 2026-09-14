import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Vendor Outreach",
  description: "Operator console for the AI vendor outreach platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-[#0b1120] text-slate-200 antialiased">{children}</body>
    </html>
  );
}
