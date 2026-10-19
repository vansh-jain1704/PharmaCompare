/**
 * What the photo checks found, in plain words. These are warnings about WHY a photo may read badly (blur, dark, small, faint): they never
 * block an upload and never say the photo is good. "No problems detected" means only that the four checks listed found none.
 */
export default function PhotoQualityNotes({ quality, showOk = false }) {
  if (!quality) return null;
  const warnings = Array.isArray(quality.warnings) ? quality.warnings : [];
  if (warnings.length === 0) {
    if (!showOk) return null;
    return (
      <p className="tiny subtle">
        Photo checks ({(quality.checked || []).join(", ")}) found no problems. That does not guarantee every word was read correctly.
      </p>
    );
  }
  return (
    <div className="alert alert-warn" role="note" style={{ textAlign: "left" }}>
      <div>
        <strong>About the photo</strong>
        <ul className="bullets" style={{ margin: "0.3rem 0 0" }}>
          {warnings.map((w) => <li key={w.code}>{w.text}</li>)}
        </ul>
        <p className="tiny" style={{ margin: "0.4rem 0 0" }}>This is a warning only. Anything that could not be read is marked for you to check, never guessed.</p>
      </div>
    </div>
  );
}
