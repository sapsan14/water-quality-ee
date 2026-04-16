import DashboardLoader from "./components/DashboardLoader";
import WebVitalsReporter from "./components/WebVitalsReporter";

// The ~7 MB snapshot is now fetched client-side (see DashboardLoader +
// lib/snapshot-client). Keeping page.tsx as a lean server component means
// the RSC payload stays tiny, the snapshot file is cacheable at the CDN
// edge, and hydration starts seconds earlier on mobile networks.
export default function HomePage() {
  const currentYear = new Date().getFullYear();
  return (
    <main className="page">
      <WebVitalsReporter />
      <DashboardLoader />
      <footer className="footerNote">
        <p>
          &copy; {currentYear} H2O Atlas &middot;{" "}
          <a href="https://github.com/sapsan14/water-quality-ee" target="_blank" rel="noreferrer">GitHub</a>
          {" "}&middot; TalTech Masin&otilde;pe 2026
        </p>
        <p className="footerSub">
          Data: <a href="https://vtiav.sm.ee" target="_blank" rel="noreferrer">Terviseamet</a> open data &middot; ML decision support, not medical advice
        </p>
      </footer>
    </main>
  );
}
