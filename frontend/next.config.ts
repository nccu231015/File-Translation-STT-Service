import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL || "http://172.16.2.68:8000";

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
        source: "/stt",
        destination: `${BACKEND_URL}/stt`,
      },
      {
        source: "/pdf-translation",
        destination: `${BACKEND_URL}/pdf-translation`,
      },
      {
        source: "/factory-chat",
        destination: `${BACKEND_URL}/factory-chat`,
      },
      {
        source: "/employee-records",
        destination: `${BACKEND_URL}/employee-records`,
      },
      {
        source: "/api/employee-records",
        destination: `${BACKEND_URL}/api/employee-records`,
      },
    ];
  },
};

export default nextConfig;
