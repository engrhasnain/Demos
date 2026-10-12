/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The development badge sits on top of the sidebar; this is a product being
  // demonstrated, not a page being debugged.
  devIndicators: false,
  // The interface talks to the FastAPI backend. Set NEXT_PUBLIC_API_URL to
  // point somewhere other than the local one.
  // Production builds read an empty value from .env.production, which keeps
  // every request relative (/api/... on the same origin).
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8002",
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
