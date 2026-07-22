/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',   // enables .next/standalone for Docker deployment (Part 1 infra)
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
