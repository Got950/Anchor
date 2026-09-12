import type { Metadata } from "next";

export const metadata: Metadata = { title: "Craftify Support Assistant" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          background: "#0b0f16",
          color: "#e2e8f0",
          fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif",
        }}
      >
        {children}
      </body>
    </html>
  );
}
