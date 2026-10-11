import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";

// Paths served by Django. In the demo the tunnel routes them before they reach
// Next.js (ADR 0006); in development these rewrites do the same job.
const djangoPrefixes = ["api", "admin", "media", "static", "webhooks"];

const nextConfig: NextConfig = {
  // The dev server blocks its own resources (HMR, chunks) for unknown origins:
  // 127.0.0.1 (worktree on :3001) and the tunnel, which also serves dev mode.
  allowedDevOrigins: ["127.0.0.1", "localhost", "corpotex.oscargicast.com"],
  // The floating dev badge covers the menu, and the dashboard gets projected.
  devIndicators: false,
  // Django URLs end with a slash (ADR 0009). Without this, Next.js answers
  // /api/clock/ with a 308 to /api/clock and Django never sees the slash.
  skipTrailingSlashRedirect: true,
  // Onboarding and the style history now live under Configuración (Oscar, 10/10 23:45).
  async redirects() {
    return [
      { source: "/onboarding", destination: "/settings", permanent: true },
      { source: "/onboarding/:step", destination: "/settings/:step", permanent: true },
      { source: "/style", destination: "/settings/style", permanent: true },
    ];
  },
  async rewrites() {
    return djangoPrefixes.flatMap((prefix) => [
      { source: `/${prefix}/:path*/`, destination: `${apiUrl}/${prefix}/:path*/` },
      { source: `/${prefix}/:path*`, destination: `${apiUrl}/${prefix}/:path*` },
    ]);
  },
};

export default nextConfig;
