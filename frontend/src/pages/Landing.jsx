import { Link } from "react-router-dom";
import { ArrowRight, Search } from "lucide-react";
import SiteHeader from "../components/SiteHeader";
import PrescriptionScanner from "../components/landing/PrescriptionScanner";

/**
 * Deliberately sparse: one message, two actions, and the scanner as the
 * visual focus. No statistics, no feature grid.
 */
export default function Landing() {
  return (
    <div className="page landing">
      <SiteHeader />

      <main className="grow">
        <section className="hero">
          <div className="shell hero-grid">
            <div className="hero-copy">
              <h1 className="hero-title rise">
                From Prescription to <span className="hero-accent">Better Decisions.</span>
              </h1>
              <p className="hero-sub rise d1">
                Understand your medicines, compare prices, discover alternatives and make informed
                decisions, all from one photo of your prescription.
              </p>
              <div className="hero-actions rise d2">
                <Link to="/upload" className="btn btn-primary btn-lg">Analyze Prescription <ArrowRight size={17} /></Link>
                <Link to="/search" className="btn btn-secondary btn-lg"><Search size={17} /> Explore Medicines</Link>
              </div>
              <p className="hero-fine rise d3">Prices come from a community dataset, not live pharmacy stock.</p>
            </div>

            <div className="hero-visual rise d1"><PrescriptionScanner /></div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="shell site-footer-inner">
          <span>PharmaCompare never replaces your doctor's prescription and does not diagnose.</span>
          <Link to="/about">About &amp; limitations</Link>
        </div>
      </footer>
    </div>
  );
}
