/** @type {import('next').NextConfig} */
const nextConfig =
  process.env.NEXT_PUBLIC_LANDING_ONLY === "true"
    ? {
        output: "export",
        trailingSlash: true,
        basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
        images: { unoptimized: true },
      }
    : {};

export default nextConfig;
