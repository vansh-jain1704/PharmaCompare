/** True when at least one note says the product's fields do not fit together or something important is missing. */
export function hasWarning(notes) {
  return Array.isArray(notes) && notes.some((n) => n.level === "warn");
}
