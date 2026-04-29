import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: "https://h2oatlas.ee/sitemap.xml",
    host: "https://h2oatlas.ee",
  };
}
