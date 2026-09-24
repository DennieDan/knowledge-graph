import type { MetadataRoute } from "next";
import { landingOnly, siteUrl } from "./lib/site";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: landingOnly
      ? [{ userAgent: "*", allow: "/" }]
      : [{ userAgent: "*", allow: "/landing", disallow: "/" }],
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  };
}
