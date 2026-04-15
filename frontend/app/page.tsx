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
        <p>© {currentYear} H2O Atlas. Open data + ML decision support.</p>
      </footer>
    </main>
  );
}
