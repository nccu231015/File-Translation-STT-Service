import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  experimental: {
    serverActions: {
      allowedOrigins: ["*"],
    },
  },
  async rewrites() {
    return [
      // Proxy all known backend endpoints through Next.js server
      // This eliminates CORS entirely — browser only sees port 3000
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
      {
        source: "/factory-chat",
        destination: `${BACKEND_URL}/factory-chat`,
      },
      {
        source: "/api/employee-records",
        destination: `${BACKEND_URL}/api/employee-records`,
      },
      {
        source: "/api/records/:path*",
        destination: `${BACKEND_URL}/api/records/:path*`,
      },
      {
        source: "/factory-sessions",
        destination: `${BACKEND_URL}/factory-sessions`,
      },
      {
        source: "/factory-sessions/:path*",
        destination: `${BACKEND_URL}/factory-sessions/:path*`,
      },
    ];
  },
};

export default nextConfig;
