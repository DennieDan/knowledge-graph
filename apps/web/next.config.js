import process from "node:process";

// Production serves the API from this app's own origin at /backend, proxied to
// Render, so the session cookie is first-party in every browser. Once the API has
// a same-site custom domain, point NEXT_PUBLIC_API_URL at it and unset API_PROXY_TARGET.
const apiUrl = process.env.NEXT_PUBLIC_API_URL;
const proxyTarget = process.env.API_PROXY_TARGET?.replace(/\/+$/, "");

if (process.env.VERCEL_ENV === "production") {
  if (!apiUrl) throw new Error("NEXT_PUBLIC_API_URL must be set for production builds");
  if (apiUrl.startsWith("/") && !proxyTarget) {
    throw new Error("API_PROXY_TARGET must be set when NEXT_PUBLIC_API_URL is a relative path");
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    if (!proxyTarget || !apiUrl?.startsWith("/")) return [];
    return [{ source: `${apiUrl}/:path*`, destination: `${proxyTarget}/:path*` }];
  },
};

export default nextConfig;
