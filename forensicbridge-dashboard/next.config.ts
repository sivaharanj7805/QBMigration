import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy /health and /api requests to the Flask backend when BACKEND_URL is set.
  // This prevents redirect loops when the frontend and backend share a domain
  // (e.g., Next.js on Vercel proxying to Flask on EC2/ALB).
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL;
    if (!backendUrl) {
      return [];
    }
    return [
      {
        source: '/health',
        destination: `${backendUrl}/health`,
      },
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
