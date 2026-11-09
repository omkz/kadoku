import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${process.env.API_PROXY_TARGET || "http://localhost:8000"}/:path*` }];
  },
};

export default nextConfig;
