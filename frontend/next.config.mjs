/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  experimental: {
    turbopackRoot: ".",
  },

  async headers() {
    const isDev = process.env.NODE_ENV !== "production";
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
              // React dev needs unsafe-eval; production doesn't
              isDev
                ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
                : "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
              "connect-src 'self' http://localhost:8000 http://localhost:8888 http://localhost:3200 ws://localhost:3200",
              "frame-src 'self' https://www.openstreetmap.org https://www.google.com",
              "worker-src 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },

  async rewrites() {
    const apiUrl =
      process.env.INTERNAL_API_URL || "http://localhost:8888";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
