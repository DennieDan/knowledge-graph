import process from "node:process";

// Production serves the API from this app's own origin at /backend, proxied to
// Render, so the session cookie is first-party in every browser. Once the API has
// a same-site custom domain, point NEXT_PUBLIC_API_URL at it and unset API_PROXY_TARGET.
const apiUrl = process.env.NEXT_PUBLIC_API_URL;
const proxyTarget = process.env.API_PROXY_TARGET?.replace(/\/+$/, "");
const posthogHost = (process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com").replace(/\/+$/, "");
const posthogAssets = posthogHost.replace(/:\/\/(\w+)\.i\./, "://$1-assets.i.");
const landingOnly = process.env.NEXT_PUBLIC_LANDING_ONLY === "true";
// GitHub Pages cannot run a Next server; a Vercel landing deployment can.
const staticExport = process.env.LANDING_STATIC_EXPORT === "true";

if (process.env.VERCEL_ENV === "production" && !landingOnly) {
  if (!apiUrl) throw new Error("NEXT_PUBLIC_API_URL must be set for production builds");
  if (apiUrl.startsWith("/") && !proxyTarget) {
    throw new Error("API_PROXY_TARGET must be set when NEXT_PUBLIC_API_URL is a relative path");
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = staticExport
  ? {
      // Static export for GitHub Pages; rewrites and proxying cannot run there.
      output: "export",
      trailingSlash: true,
      basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
      images: { unoptimized: true },
    }
  : landingOnly
  ? {
      async redirects() {
        // One indexable URL for the landing page: the root.
        return [{ source: "/landing", destination: "/", permanent: true }];
      },
      async rewrites() {
        // The landing page is the whole site here, so it answers at the root
        // instead of the workspace redirect in app/page.tsx.
        return {
          beforeFiles: [{ source: "/", destination: "/landing" }],
          afterFiles: [],
          fallback: [],
        };
      },
    }
  : {
      // PostHog API paths rely on trailing slashes.
      skipTrailingSlashRedirect: true,
      async rewrites() {
        // Analytics is proxied first-party so tracking blockers don't drop events.
        const analytics = [
          { source: "/ingest/static/:path*", destination: `${posthogAssets}/static/:path*` },
          { source: "/ingest/:path*", destination: `${posthogHost}/:path*` },
        ];
        if (!proxyTarget || !apiUrl?.startsWith("/")) return analytics;
        return [...analytics, { source: `${apiUrl}/:path*`, destination: `${proxyTarget}/:path*` }];
      },
    };

export default nextConfig;
