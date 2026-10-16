import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return ["/auth/verify-email", "/auth/reset-password", "/auth/error", "/auth/complete-registration", "/auth/confirm-google-link"].map(source => ({
      source,
      headers: [
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Cache-Control", value: "no-store" },
        { key: "X-Robots-Tag", value: "noindex, nofollow" },
      ],
    }));
  },
  async rewrites() {
    return [{
      source: "/api/:path*",
      destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*`,
    }];
  },
};

export default nextConfig;
