import "./globals.css";
import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans, Manrope, Space_Grotesk } from "next/font/google";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  display: "swap",
  variable: "--font-latin-ui"
});

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin", "cyrillic"],
  weight: ["400", "600", "700"],
  display: "swap",
  variable: "--font-cyrillic-ibm"
});

const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  weight: ["400", "600", "700"],
  display: "swap",
  variable: "--font-cyrillic-manrope"
});

const DEFAULT_OG_IMAGE = "/og-default.png";

export const metadata: Metadata = {
  title: "H2O Atlas \u2014 Water Quality Map of Estonia",
  description:
    "Interactive map of Estonian water quality powered by Terviseamet open data and ML risk assessments. 69,000+ samples across swimming, drinking water, pools, and source domains.",
  icons: {
    icon: "/favicon.svg",
    apple: "/apple-touch-icon.png",
  },
  manifest: "/manifest.webmanifest",
  metadataBase: new URL("https://h2oatlas.ee"),
  openGraph: {
    title: "H2O Atlas \u2014 Water Quality Map of Estonia",
    description:
      "Interactive map of Estonian water quality powered by Terviseamet open data and ML risk assessments.",
    url: "https://h2oatlas.ee",
    siteName: "H2O Atlas",
    locale: "en",
    type: "website",
    images: [{ url: DEFAULT_OG_IMAGE, width: 1200, height: 630, alt: "H2O Atlas \u2014 Water Quality Map of Estonia" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "H2O Atlas \u2014 Water Quality Map of Estonia",
    description:
      "Interactive map of Estonian water quality powered by open data and ML assessments.",
    images: [DEFAULT_OG_IMAGE],
  },
  alternates: {
    languages: {
      ru: "https://h2oatlas.ee",
      et: "https://h2oatlas.ee",
      en: "https://h2oatlas.ee",
    },
  },
};

// Schema.org JSON-LD: lets Google pick up the site for Dataset Search and
// improves rich-result eligibility (sitelinks, breadcrumb). Two top-level
// graph nodes: a WebSite (search intent) and a Dataset (open-data discovery).
const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": "https://h2oatlas.ee/#website",
      url: "https://h2oatlas.ee",
      name: "H2O Atlas",
      description: "Interactive map of Estonian water quality powered by Terviseamet open data and ML risk assessments.",
      inLanguage: ["et", "ru", "en"],
    },
    {
      "@type": "Dataset",
      "@id": "https://h2oatlas.ee/#dataset",
      name: "H2O Atlas \u2014 Estonian Water Quality Snapshot",
      description: "Aggregated and ML-scored snapshot of Estonian water quality samples (swimming, drinking water, pools, sources) from Terviseamet open data.",
      url: "https://h2oatlas.ee",
      keywords: ["water quality", "Estonia", "Terviseamet", "open data", "machine learning"],
      license: "https://creativecommons.org/licenses/by/4.0/",
      isAccessibleForFree: true,
      creator: { "@type": "Organization", name: "TalTech Masin\u00f5pe 2026" },
      sourceOrganization: { "@type": "Organization", name: "Terviseamet", url: "https://vtiav.sm.ee" },
      spatialCoverage: { "@type": "Place", name: "Estonia" },
    },
  ],
};

// Explicit mobile viewport — Next 16 no longer injects a default tag, so
// without this mobile Safari renders at 980px desktop width and every
// CSS media query in globals.css misfires.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5, // do not lock to 1 — blocks pinch-zoom accessibility
  viewportFit: "cover", // lets env(safe-area-inset-*) take effect on notched iPhones
  themeColor: [
    // Match --bg tokens in globals.css (light: #f3f7fb, dark: #0b1220)
    { media: "(prefers-color-scheme: light)", color: "#f3f7fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" }
  ]
};

// Inline FOUC-prevention script — applies the saved theme to <body>
// before React hydrates, so users do not see a light flash on dark devices
// (or vice versa) and the mobile shell does not blink between themes.
const themeBootstrap = `(() => {
  try {
    var t = localStorage.getItem('water.ui.theme.v1');
    if (t === 'dark') document.documentElement.dataset.theme = 'dark';
  } catch (e) {}
})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className={`${spaceGrotesk.variable} ${ibmPlexSans.variable} ${manrope.variable} cyr-ibm`}>{children}</body>
    </html>
  );
}
