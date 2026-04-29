import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "H2O Atlas",
    short_name: "H2O Atlas",
    description: "Interactive map of Estonian water quality.",
    start_url: "/",
    display: "standalone",
    background_color: "#f3f7fb",
    theme_color: "#0b1220",
    icons: [
      { src: "/favicon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
