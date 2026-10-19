// What the prescription says about dosing for this line, in one honest sentence (nothing defaulted, possible readings marked).
export function dosingSentence(ins) {
  if (!ins) return null;
  const parts = [];
  if (ins.text) parts.push(ins.text);
  else if (ins.frequency) parts.push(ins.frequency);
  const doseTiming = [ins.dose, ins.timing].filter(Boolean).join(", ");
  if (doseTiming) parts.push(doseTiming);
  if (ins.duration) parts.push(`for ${ins.duration}`);
  else if (ins.duration_unreadable) parts.push("number of days could not be read");
  return parts.length ? parts.join(" · ") : null;
}
