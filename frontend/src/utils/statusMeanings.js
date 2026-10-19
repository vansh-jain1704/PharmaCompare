/** What each status word means, in one place, so Confirmed, Suggested and Needs verification cannot be confused. */
export const STATUS_MEANINGS = [
  { tone: "ok", word: "Confirmed", text: "You chose this product yourself. It is your decision; PharmaCompare has not verified it." },
  { tone: "ok", word: "Matched", text: "Matched automatically after the name, strength and form all agreed with a product in the dataset." },
  { tone: "warn", word: "Suggested", text: "The name written is this product's name, but its strength, form or the reading still need your check. Nothing is priced or safety-checked until you confirm it." },
  { tone: "warn", word: "Needs verification", text: "No reliable match. Any products shown are only look-alikes. Nothing is priced, compared or safety-checked for this line." },
  { tone: "muted", word: "Entered by you", text: "You typed this medicine in. It is not matched to the dataset, so there is no price, saving or safety check for it." },
];
