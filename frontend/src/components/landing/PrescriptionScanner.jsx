import { GitCompareArrows, Pill, Repeat2 } from "lucide-react";

/**
 * The landing-page hero: a sample prescription inside an OCR-style scanner.
 *
 * Everything here is an illustration. The prescription is fictional and
 * labelled "Sample", and the status labels loop on a fixed timer; none of it
 * is a live result. The animation is pure CSS (one 7.2s loop) so the scan
 * line, the detection boxes and the status label stay in step, and it falls
 * back to a still frame for people who ask for reduced motion.
 */
export default function PrescriptionScanner() {
  return (
    <div
      className="scanner"
      role="img"
      aria-label="A sample prescription being scanned: the medicine names are detected and read"
    >
      <div className="scanner-stage">
        <span className="scanner-shadow" aria-hidden="true" />

        <div className="rx-tilt">
          <article className="rx" aria-hidden="true">
            <span className="rx-sample">Sample</span>

            <header className="rx-head">
              <span className="rx-clinic">
                <strong>Sample Clinic</strong>
                <small>Dr. A. Example, MBBS</small>
              </span>
              <span className="rx-cross" />
            </header>

            <div className="rx-meta">
              <span>Patient: <i className="rx-blank" /></span>
              <span>Date: <i className="rx-blank short" /></span>
            </div>

            <div className="rx-symbol">℞</div>

            <ol className="rx-lines">
              <li><span className="hand">Tab. Dolo 650</span><span className="hand dose">1 – 0 – 1  ×  5 days</span><i className="det det-1" /></li>
              <li><span className="hand">Cap. Amoxycillin 500</span><span className="hand dose">1 – 1 – 1  ×  5 days</span><i className="det det-2" /></li>
              <li><span className="hand">Tab. Pantop 40</span><span className="hand dose">1 – 0 – 0  before food</span><i className="det det-3" /></li>
            </ol>

            <footer className="rx-foot">
              <span className="rx-sign hand">A. Example</span>
              <small>Signature</small>
            </footer>

            <span className="scan-trail" />
            <span className="scan-line" />
          </article>
        </div>

        <i className="frame frame-tl" aria-hidden="true" />
        <i className="frame frame-tr" aria-hidden="true" />
        <i className="frame frame-bl" aria-hidden="true" />
        <i className="frame frame-br" aria-hidden="true" />

        <div className="chip chip-status" aria-hidden="true">
          <span className="chip-dot" />
          <span className="chip-labels">
            <span className="st st-1">Scanning prescription</span>
            <span className="st st-2">Reading prescription</span>
            <span className="st st-3">Detecting medicines</span>
            <span className="st st-4">Matching medicines</span>
          </span>
        </div>

        <div className="chip chip-feature chip-f1" aria-hidden="true"><span><Pill size={15} /></span>Medicine Detection</div>
        <div className="chip chip-feature chip-f2" aria-hidden="true"><span><GitCompareArrows size={15} /></span>Compare Prices</div>
        <div className="chip chip-feature chip-f3" aria-hidden="true"><span><Repeat2 size={15} /></span>Find Alternatives</div>
      </div>
    </div>
  );
}
