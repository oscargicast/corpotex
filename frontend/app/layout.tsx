import type { Metadata, Viewport } from "next";
import "./globals.css";

// Icons and the Open Graph image come from app/ (icon.png, favicon.ico,
// apple-icon.png, opengraph-image.png); the manifest and its icons from public/.
export const metadata: Metadata = {
  metadataBase: new URL("https://corpotex.oscargicast.com"),
  title: "Corpotex",
  description: "Órdenes, pedidos a proveedores y talleres, y alertas de Corpotex.",
  manifest: "/site.webmanifest",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#173252", // brand navy
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
