import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Unleash — Multimodal Human Verification",
  description: "Advanced active challenge-response verification against deepfakes and replay attacks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
