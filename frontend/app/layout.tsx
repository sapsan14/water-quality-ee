import "./globals.css";
import type { Metadata } from "next";
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
  title: "H2O Atlas - Water Quality Map",
  description: "Estonia water quality map powered by open data and ML assessments.",
  icons: {
    icon: "/favicon.svg"
  }
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
