import type { NextConfig } from "next";

/**
 * CSP Configuration
 *
 * SECURITY FIX: Use environment variable for API domain instead of hardcoding.
 * This allows different domains for dev, staging, and production.
 *
 * Set NEXT_PUBLIC_CSP_CONNECT_DOMAINS in your environment:
 * - Development: "http://localhost:5000"
 * - Staging: "https://api.staging.forensicbridge.ca"
 * - Production: "https://api.forensicbridge.ca https://*.forensicbridge.ca"
 */
const getConnectSrcDomains = (): string => {
  const envDomains = process.env.NEXT_PUBLIC_CSP_CONNECT_DOMAINS;
  if (envDomains) {
    return envDomains;
  }

  // Default based on environment
  if (process.env.NODE_ENV === 'development') {
    return 'http://localhost:5000 http://localhost:3000';
  }

  // Production fallback - require explicit configuration
  console.warn(
    '[Security] NEXT_PUBLIC_CSP_CONNECT_DOMAINS not set. ' +
    'Using restrictive default. Set this variable for your API domain.'
  );
  return "'none'"; // Restrictive default - API calls will fail until configured
};

const nextConfig: NextConfig = {
  // Production: standalone output for Docker deployment
  output: 'standalone',
  // HIGH-27 FIX: Add security headers including Content Security Policy
  async headers() {
    const connectSrcDomains = getConnectSrcDomains();

    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline'", // Next.js requires unsafe-inline for hydration scripts
              "style-src 'self' 'unsafe-inline'", // Required for Tailwind CSS
              "img-src 'self' data: https:",
              "font-src 'self' data:",
              `connect-src 'self' ${connectSrcDomains}`,
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join('; '),
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
          {
            // AUDIT FIX P1-05: HSTS header to prevent SSL stripping attacks
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains; preload',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
