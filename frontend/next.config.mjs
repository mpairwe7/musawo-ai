/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  // Turbopack workspace root
  experimental: {
    turbopackRoot: ".",
  },

  // PWA headers
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains",
          },
          {
            key: "Permissions-Policy",
            value: "microphone=(self), geolocation=(self), camera=()",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
              "connect-src 'self' http://localhost:8000",
              "frame-src 'self' https://www.openstreetmap.org https://www.google.com",
              "worker-src 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },

  // API proxy to backend
  async rewrites() {
    const apiUrl =
      process.env.INTERNAL_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
