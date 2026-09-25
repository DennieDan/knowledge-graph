import type { MetadataRoute } from "next";
import { landingOnly, siteUrl } from "./lib/site";

export const dynamic = "force-static";

// The workspace app is private, so only the landing deployment is crawlable.
export default function robots(): MetadataRoute.Robots {
  if (!landingOnly) return { rules: [{ userAgent: "*", disallow: "/" }] };
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  };
}
