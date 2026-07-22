/** @type {import('next').NextConfig} */

const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "img-src 'self' data: https:",
      "connect-src 'self'",
      "font-src 'self'",
      "frame-ancestors 'none'",
    ].join("; "),
  },
]

const nextConfig = {
  output: "standalone", // enables .next/standalone for Docker deployment
  typescript: {
    ignoreBuildErrors: false, // all type errors resolved
  },
  images: {
    unoptimized: true,
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }]
  },
}

export default nextConfig
