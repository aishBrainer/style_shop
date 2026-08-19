/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Docker/Render use the standalone server. Vercel’s Next.js builder
  // needs the default output — `standalone` produces a platform 404.
  ...(process.env.VERCEL ? {} : { output: 'standalone' }),

  // Signed URLs point at MinIO in development and the CDN in production.
  // next/image is not used for those (the signature would be stripped by the
  // optimizer), so this list only covers static marketing imagery.
  images: {
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost' },
      { protocol: 'https', hostname: '**' },
    ],
  },

  async rewrites() {
    // Same-origin API calls, so the httpOnly session cookie is sent without
    // any CORS or SameSite negotiation. Inside Docker the browser talks to
    // localhost:3000 and Next forwards to the api service.
    const target = process.env.API_INTERNAL_URL || 'http://localhost:8000'
    return [{ source: '/api/v1/:path*', destination: `${target}/api/v1/:path*` }]
  },

  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ]
  },
}

export default nextConfig
