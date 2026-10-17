export function rupees(amount) {
  return amount == null ? "—" : `₹${Number(amount).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDate(value, { withYear = true } = {}) {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}) });
}

const FILE_LIKE = /\.(png|jpe?g|pdf)$/i;

/**
 * What a prescription is called on screen. A name the user typed wins; a
 * raw filename (or nothing) is never the identity - it becomes
 * "Prescription — 5 Oct 2026".
 */
export function prescriptionTitle(prescription) {
  const name = (prescription?.prescription_name || "").trim();
  if (name && !FILE_LIKE.test(name)) return name;
  const date = formatDate(prescription?.upload_date);
  return date ? `Prescription — ${date}` : "Prescription";
}
