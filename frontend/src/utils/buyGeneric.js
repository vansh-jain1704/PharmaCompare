/**
 * "Buy Generic": a link that searches the web for a product by its ACTIVE INGREDIENTS, each with its strength, and its dosage form: never by a brand
 * and never by a guess.
 *
 * What this is and is not:
 *   - It builds a Google Shopping search URL. Nothing is fetched, so nothing here knows a price, a stock level or whether a shop sells the product,
 *     and nothing says so. The result is whatever the search shows; the person checks each product's ingredients, strength and form.
 *   - It only produces a link for a medicine whose ingredients are KNOWN: a catalogue product with a complete ingredient list, a strength for every
 *     ingredient and a dosage form, and, on a prescription, a line that is settled. Anything else is "verify first" with the reason, never a
 *     search built from a guess.
 *   - It never substitutes: the search is for the SAME ingredients, strengths and form (and release type, so a sustained-release tablet is not
 *     searched as a plain one). Whether a result is equivalent is for the person, the doctor or the pharmacist.
 *
 * All pure, so the wording and the URL are tested without a browser.
 */

export const SEARCH_BASE = "https://www.google.com/search";
export const SEARCH_SITE = "Google Shopping";
export const MAX_QUERY_CHARS = 250;

const MISSING = new Set(["", "na", "n/a", "nan", "none", "null", "-"]);
const isMissing = (value) => value == null || MISSING.has(String(value).trim().toLowerCase());

const RELEASE_WORDS = {
  sr: "sustained release", er: "extended release", cr: "controlled release", pr: "prolonged release", mr: "modified release",
  dt: "dispersible", odt: "mouth dissolving", chewable: "chewable", ec: "enteric coated", modified: "modified release",
};

// Some products carry a drug CLASS where an ingredient belongs ("Oxytocics And Prostaglandin ... And Products For Cervical Dilatation",
// "Trimethoprim Combinations", "Gynaecological Products"). A search for a class is not a search for an active ingredient, so it is refused.
const CLASS_LIKE_NAME = /\b(products?|combinations?|including other)\b/i;

// What the server's own data notes (data_validation_service) mean for a search: the ingredients or form cannot be relied on.
const BLOCKING_NOTES = {
  no_composition: "No ingredient information is on file for this product.",
  ingredient_list_incomplete: "The ingredient list for this product is incomplete in the dataset.",
  strength_not_in_composition: "The strength in the product's name could not be matched to its ingredient strengths.",
  no_form: "The dosage form is not on file.",
};

/** [{ name, strength }] from "Amoxycillin (500mg) + Clavulanic Acid (125mg)". strength is null when the ingredient has none written. */
export function parseComposition(composition) {
  if (isMissing(composition)) return [];
  return clean(composition).split(/\s\+\s/).map((part) => {
    // The strength is the LAST bracket and holds no bracket itself, so a name that carries its own bracket stays whole:
    // "Progesterone (Natural Micronized) (25mg)" is the ingredient "Progesterone (Natural Micronized)" at "25mg".
    const match = part.match(/^\s*(.*?)\s*\(([^()]*)\)\s*$/);
    const name = (match ? match[1] : part).replace(/\s+/g, " ").trim();
    const strength = match ? match[2].replace(/\s+/g, " ").trim() : "";
    return { name, strength: /\d/.test(strength) ? strength : null };
  }).filter((p) => p.name);
}

function clean(text) {
  // eslint-disable-next-line no-control-regex
  return String(text).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * The search for a catalogue product (a search result, or a settled prescription line's product), or the reason there is not one.
 * `medicine` needs composition, form and (optionally) release_type / release_label / composition_incomplete; `notes` are the server's data notes.
 * Returns { ok: true, query, url, ingredients, form } or { ok: false, reason }.
 */
export function productBuyGeneric(medicine, notes = medicine?.data_notes) {
  if (!medicine) return { ok: false, reason: "There is no medicine to search for." };
  if (isMissing(medicine.composition)) return { ok: false, reason: BLOCKING_NOTES.no_composition };
  if (medicine.composition_incomplete) return { ok: false, reason: BLOCKING_NOTES.ingredient_list_incomplete };
  const blocking = (Array.isArray(notes) ? notes : []).find((n) => BLOCKING_NOTES[n.code]);
  if (blocking) return { ok: false, reason: BLOCKING_NOTES[blocking.code] };

  const ingredients = parseComposition(medicine.composition);
  if (!ingredients.length) return { ok: false, reason: BLOCKING_NOTES.no_composition };
  if (ingredients.some((i) => !i.strength)) return { ok: false, reason: "A strength is missing for at least one ingredient, so the product cannot be searched safely." };
  const classLike = ingredients.find((i) => CLASS_LIKE_NAME.test(i.name));
  if (classLike) return { ok: false, reason: `The ingredient on file (“${classLike.name}”) looks like a drug class, not a specific ingredient, so the product cannot be searched safely.` };
  if (isMissing(medicine.form)) return { ok: false, reason: BLOCKING_NOTES.no_form };

  const release = medicine.release_label || (medicine.release_type ? RELEASE_WORDS[medicine.release_type] || "modified release" : "");
  const query = clean([
    ingredients.map((i) => `${i.name} ${i.strength}`).join(" and "),
    String(medicine.form).toLowerCase(),
    release ? String(release).toLowerCase() : "",
  ].filter(Boolean).join(" "));
  if (query.length > MAX_QUERY_CHARS) return { ok: false, reason: "The product has too many ingredients to search for reliably." };

  const url = new URL(SEARCH_BASE);
  url.searchParams.set("tbm", "shop");       // the Shopping tab
  url.searchParams.set("q", query);
  url.searchParams.set("hl", "en");
  url.searchParams.set("gl", "in");          // results for India
  return { ok: true, query, url: url.toString(), ingredients, form: String(medicine.form).toLowerCase() };
}

/**
 * The same for a line of a prescription's table. A line that is only suggested, still needs verification, was typed in, or whose match still
 * needs a check is NOT searched: the reason says why, and the person is asked to verify the medicine first.
 */
export function rowBuyGeneric(row) {
  if (!row) return { ok: false, reason: "There is no medicine to search for." };
  if (row.userEntered) return { ok: false, reason: "You entered this medicine yourself, so it is not matched to an ingredient list in the dataset." };
  if (!row.doctorMedicine) {
    if (row.suggested) return { ok: false, reason: `This line is only suggested (${row.suggestion?.medicine_name || "a product"}), not confirmed.` };
    if (row.userUnmatched) return { ok: false, reason: "You marked this line as not identified." };
    return { ok: false, reason: "This line has not been identified yet." };
  }
  if (row.needsDisambiguation) return { ok: false, reason: "More than one product fits this line, so the strength or form is not settled." };
  if (row.ocrUncertain) return { ok: false, reason: "The text of this line was read with low confidence." };
  if (row.needsCheck) return { ok: false, reason: "This match still needs your check against the prescription." };
  if (row.confirmedWithConflicts) return { ok: false, reason: "The product you confirmed differs from what the prescription line says." };
  return productBuyGeneric(row.doctorMedicine, row.dataNotes);
}

/** Shown wherever the button is explained (the medicine drawer and a line's detail). Says what the link does and what it does not know. */
export const BUY_GENERIC_NOTE =
  `Buy Generic opens a ${SEARCH_SITE} search in a new tab for the active ingredients, strength and form. The results may include different brands: ` +
  "check the ingredients, strength and form of each product before buying. PharmaCompare has not checked the results and shows no price, availability or stock for them.";
