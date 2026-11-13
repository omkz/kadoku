import type { NextConfig } from "next";

const apiTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Browser requests stay same-origin. Unified Render serves the API locally.
      { source: "/backend/:path*", destination: `${apiTarget}/:path*` },
      // Also preserve direct API/webhook URLs during the single-service cutover.
      { source: "/api/v1/:path*", destination: `${apiTarget}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
