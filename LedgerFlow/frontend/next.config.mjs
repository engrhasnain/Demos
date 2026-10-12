/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The development badge sits on top of the sidebar; this is a product being
  // demonstrated, not a page being debugged.
  devIndicators: false,
  // The interface talks to the FastAPI backend. Set NEXT_PUBLIC_API_URL to
  // point somewhere other than the local one.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001",
  },
};

export default nextConfig;
