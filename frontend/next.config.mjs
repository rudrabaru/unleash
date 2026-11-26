// The browser calls /api/v1 on its own origin and Next forwards it to the backend: no CORS,
// and no mixed content behind HTTPS. Set API_ORIGIN when the backend is not on this machine,
// e.g. API_ORIGIN=http://192.168.0.20:8000 (server-side only).
const apiOrigin = (process.env.API_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "");
const isDev = process.env.NODE_ENV !== "production";

// A page that turns on the camera must not run foreign code or be framed by another site (a framed
// page could trick someone into granting camera access). Next injects inline bootstrap scripts, so
// 'unsafe-inline' stays for scripts; the dev server also needs eval and its websocket.
function connectSources() {
  const sources = ["'self'"];
  const direct = process.env.NEXT_PUBLIC_API_BASE_URL || "";
  if (/^https?:\/\//i.test(direct)) sources.push(new URL(direct).origin); // a browser calling the API directly
  if (isDev) sources.push("ws:", "wss:");
  return sources.join(" ");
}

const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "font-src 'self' data:",
  `connect-src ${connectSources()}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  // The camera and microphone for this site only; nothing else.
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=(), payment=(), usb=()" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
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
