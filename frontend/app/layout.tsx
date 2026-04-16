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

export const metadata: Metadata = {
  title: "H2O Atlas \u2014 Water Quality Map of Estonia",
  description:
    "Interactive map of Estonian water quality powered by Terviseamet open data and ML risk assessments. 69,000+ samples across swimming, drinking water, pools, and source domains.",
  icons: { icon: "/favicon.svg" },
  metadataBase: new URL("https://h2oatlas.ee"),
  openGraph: {
    title: "H2O Atlas \u2014 Water Quality Map of Estonia",
    description:
      "Interactive map of Estonian water quality powered by Terviseamet open data and ML risk assessments.",
    url: "https://h2oatlas.ee",
    siteName: "H2O Atlas",
    locale: "en",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "H2O Atlas \u2014 Water Quality Map of Estonia",
    description:
      "Interactive map of Estonian water quality powered by open data and ML assessments.",
  },
  alternates: {
    languages: {
      ru: "https://h2oatlas.ee",
      et: "https://h2oatlas.ee",
      en: "https://h2oatlas.ee",
    },
  },
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
      </head>
      <body className={`${spaceGrotesk.variable} ${ibmPlexSans.variable} ${manrope.variable} cyr-ibm`}>{children}</body>
    </html>
  );
}
