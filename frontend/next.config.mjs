// The browser calls /api/v1 on its own origin and Next forwards it to the backend: no CORS,
// and it works from a phone over HTTPS (no mixed content). Set API_ORIGIN when the backend is
// not on this machine, e.g. API_ORIGIN=http://192.168.0.20:8000 (server-side only).
const apiOrigin = (process.env.API_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
