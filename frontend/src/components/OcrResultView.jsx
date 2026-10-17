import { useState } from "react";

/**
 * Renders an OCR result line-by-line, flagging low-confidence lines instead
 * of hiding or "correcting" them. The raw text (exactly what EasyOCR
 * returned, unmodified) stays available behind a toggle, per the rule that
 * we never invent or silently fix medical text.
 */
export default function OcrResultView({ lines, rawText, confidence }) {
  const [showRaw, setShowRaw] = useState(false);
  const hasLines = Array.isArray(lines) && lines.length > 0;
  const uncertainCount = hasLines ? lines.filter((l) => l.uncertain).length : 0;

  return (
    <div className="ocr-result">
      {typeof confidence === "number" && (
        <p className="ocr-confidence">
          <strong>Overall confidence:</strong> {(confidence * 100).toFixed(1)}%
        </p>
      )}

      {uncertainCount > 0 && (
        <div className="alert alert-warning">
          {uncertainCount} line{uncertainCount > 1 ? "s" : ""} below may be misread -
          please check them against the original prescription before relying on them.
        </div>
      )}

      {hasLines ? (
        <ul className="ocr-line-list">
          {lines.map((line, i) => (
            <li key={i} className={`ocr-line ${line.uncertain ? "ocr-line-uncertain" : ""}`}>
              <span className="ocr-line-text">{line.text}</span>
              <span className="ocr-line-confidence">
                {line.uncertain && <span className="uncertain-flag" title="Low confidence reading">⚠</span>}
                {(line.confidence * 100).toFixed(0)}%
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="page-subtitle">No formatted lines available for this result.</p>
      )}

      <button type="button" className="link-button" onClick={() => setShowRaw((v) => !v)}>
        {showRaw ? "Hide raw OCR text" : "Show raw OCR text"}
      </button>
      {showRaw && <pre className="extracted-text">{rawText || "(no text extracted)"}</pre>}
    </div>
  );
}
