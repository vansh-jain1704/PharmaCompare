"""
What an alternative's price comparison does and does not establish, said once and in the same words on the screen and in the PDF.

An alternative is a different product with the SAME active ingredients, each at the same strength, the same dosage form and the same release
type (enforced in the database query, see price_model.find_alternatives). That is all the dataset can say. It cannot say anything about what
differs between brands, so that is listed rather than left out. Nothing here is a recommendation to switch: that is for the prescriber or the
pharmacist.
"""

MATCHED = (
    "the same active ingredients, each at the same strength",
    "the same dosage form",
    "the same release type (a conventional product is never offered for a modified-release one, or the other way round)",
)
NOT_COMPARED = (
    "inactive ingredients (fillers, colours, coatings), which differ between brands",
    "the manufacturer's quality, or whether two brands are absorbed the same way",
    "whether your pharmacy stocks the product, unless a pharmacy has reported it",
)
SAFETY_CARRIES_OVER = (
    "The active ingredients are the same as the prescribed medicine's, so its interaction and allergy checks apply to these products unchanged. "
    "Check the allergy alert on the prescribed medicine before any change."
)
ASK_FIRST = "Do not change a prescribed medicine on your own: ask your doctor or pharmacist first."
INFORMATION_ONLY = "This line is not settled yet, so these alternatives are shown for information only and no saving is counted for it."


def notes_for(needs_check=False, ocr_uncertain=False, needs_disambiguation=False, confirmed_with_conflicts=False):
    """The notes to show beside a medicine's alternatives. `information_only` is True when the line itself still needs the person's check."""
    return {
        "matched": list(MATCHED),
        "not_compared": list(NOT_COMPARED),
        "safety": SAFETY_CARRIES_OVER,
        "ask_first": ASK_FIRST,
        "information_only": INFORMATION_ONLY if (needs_check or ocr_uncertain or needs_disambiguation or confirmed_with_conflicts) else None,
    }
