import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nabi AI — Montage Vidéo Automatisé",
  description:
    "Outil de montage vidéo automatisé par IA. Transcription, B-roll, zooms dynamiques, images IA — le tout en local.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
