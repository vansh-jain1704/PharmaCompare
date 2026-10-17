"""
The vocabulary for how a prescription line came to point at a medicine.

Kept in one place because several modules have to agree on the question
"is this line settled enough to analyse?" - the Clinical Decision Engine,
Price Comparison and Generic Recommendation all refuse to run against a
line that is still only a guess.
"""

# The fuzzy matcher cleared its confidence bar on its own.
MATCHED = "matched"
# A person looked at the line and said what it is. This is the STRONGEST
# signal available - stronger than any similarity score - so it must be
# treated as at least as trustworthy as MATCHED everywhere.
USER_CONFIRMED = "user_confirmed"
# Closest guess only. Never analysed, never priced, never presented as fact.
NEEDS_VERIFICATION = "needs_verification"

CONFIRMED_STATUSES = frozenset({MATCHED, USER_CONFIRMED})


def is_confirmed(match_status):
    return match_status in CONFIRMED_STATUSES
