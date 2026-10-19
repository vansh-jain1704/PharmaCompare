// The rules for typing in a medicine the dataset cannot identify. Pure, so they are tested without a browser.

// The same list the server accepts (backend/app/services/manual_entry_service.py FORMS).
export const ENTRY_FORMS = ["Tablet", "Capsule", "Syrup", "Injection", "Drops", "Cream / ointment", "Powder / sachet", "Inhaler", "Other"];

export const EMPTY_DETAILS = { name: "", strength: "", form: "", schedule: "", duration: "" };

/** The details to show first: what the person typed before, otherwise empty (nothing is pre-filled from a guess). */
export function initialDetails(row) {
  const typed = row?.userEntered;
  return typed
    ? { name: typed.name || "", strength: typed.strength || "", form: typed.form || "", schedule: typed.schedule || "", duration: typed.duration || "" }
    : EMPTY_DETAILS;
}

/** The first problem with the typed details, or null. Mirrors the server's rules; the server decides. */
export function detailsProblem(details) {
  if ((details.name || "").trim().length < 2) return "Enter the medicine name (at least 2 characters).";
  const limits = [["name", 100, "Medicine name"], ["strength", 40, "Strength"], ["schedule", 100, "Schedule"], ["duration", 100, "Duration"]];
  for (const [key, limit, label] of limits) if ((details[key] || "").trim().length > limit) return `${label} must be at most ${limit} characters.`;
  return null;
}
