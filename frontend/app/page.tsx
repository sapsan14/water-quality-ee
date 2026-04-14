import Image from "next/image";
import Dashboard from "./components/Dashboard";
import LocalizedSubtitle from "./components/LocalizedSubtitle";
import WebVitalsReporter from "./components/WebVitalsReporter";
import type { FrontendSnapshot } from "./lib/types";

async function loadSnapshot(): Promise<FrontendSnapshot> {
  // Build-time/local fallback that also works for static hosting on Cloudflare Pages.
  const { readFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  const raw = await readFile(join(process.cwd(), "public", "data", "snapshot.frontend.json"), "utf-8");
  return JSON.parse(raw) as FrontendSnapshot;
}

export default async function HomePage() {
  const snapshot = await loadSnapshot();
  const currentYear = new Date().getFullYear();
  return (
    <main className="page">
      <header className="header">
        <div className="brandBlock">
          <Image src="/logo.svg" alt="H2O Atlas logo" className="brandLogo" width={40} height={40} priority />
          <div>
            <h1 className="title">H2O Atlas</h1>
            <p className="subtitle">
              <LocalizedSubtitle />
            </p>
          </div>
        </div>
      </header>
      <WebVitalsReporter />
      <Dashboard snapshot={snapshot} />
      <footer className="footerNote">
        <p>© {currentYear} H2O Atlas. Open data + ML decision support.</p>
      </footer>
    </main>
  );
}
