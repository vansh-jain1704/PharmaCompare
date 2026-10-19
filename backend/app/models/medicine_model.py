import json

from app.db import get_connection
from app.services import match_status, medicine_search

# How many FULLTEXT candidates to pull before Python-side fuzzy scoring
# picks the best one. Kept generous since FULLTEXT is only used for cheap
# candidate retrieval, not the final decision.
CANDIDATE_LIMIT = 15

# Per-word cap for the brand-name prefix lookup that runs alongside FULLTEXT.
NAME_PREFIX_LIMIT = 25

# How much of a search term to keep when a literal search finds nothing, so
# an alternate salt spelling ("Amoxicillin" vs the dataset's "Amoxycillin")
# still resolves. Short enough to survive the differing letter, long enough
# not to collapse unrelated drugs together.
SPELLING_FALLBACK_PREFIX_LEN = 4

# Wider net for the coarser stem query. Scoring, not SQL ordering, decides
# the winner - these rows are only made available to be considered.
STEM_FALLBACK_LIMIT = 200


def search_candidates(boolean_query):
    """
    Runs a MySQL FULLTEXT BOOLEAN MODE search (supports trailing '*'
    wildcards) across medicine_name + composition. Returns a list of
    candidate medicine rows, most relevant first. Never invents a result -
    if nothing matches, returns an empty list.
    """
    if not boolean_query.strip():
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT medicine_id, medicine_name, composition, form, strength,
                      primary_salt, secondary_salt, manufacturer, pack_size,
                      price, is_discontinued, release_type, composition_incomplete,
                      MATCH(medicine_name, composition) AGAINST (%s IN BOOLEAN MODE) AS relevance
               FROM Medicines
               WHERE MATCH(medicine_name, composition) AGAINST (%s IN BOOLEAN MODE)
               ORDER BY relevance DESC
               LIMIT %s""",
            (boolean_query, boolean_query, CANDIDATE_LIMIT),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_family_variants(primary_salt, secondary_salt):
    """
    One representative product for every distinct (composition, form, release
    type) that exists for this ingredient set - the ground truth for "which
    strengths/forms of this medicine are there?".

    The FULLTEXT candidate list cannot answer that: for a generic name it holds
    the top few relevance hits, which are often all the same strength, so the
    other strengths never reached the matcher at all. Discontinued products and
    products whose ingredient list is known to be truncated are left out.
    """
    if not primary_salt:
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        secondary_clause = "secondary_salt = %s" if secondary_salt else "secondary_salt IS NULL"
        params = [primary_salt] + ([secondary_salt] if secondary_salt else [])
        cursor.execute(
            f"""SELECT MIN(medicine_id) AS medicine_id, COUNT(*) AS product_count
                FROM Medicines
                WHERE primary_salt = %s AND {secondary_clause}
                  AND is_discontinued = FALSE AND composition_incomplete = 0
                GROUP BY composition, form, release_type""",
            params,
        )
        groups = cursor.fetchall()
        counts = {r["medicine_id"]: r["product_count"] for r in groups}
        ids = list(counts)
        if not ids:
            return []
        placeholders = ",".join(["%s"] * len(ids))
        cursor.execute(
            f"""SELECT medicine_id, medicine_name, composition, form, strength,
                       primary_salt, secondary_salt, manufacturer, pack_size,
                       price, is_discontinued, release_type, composition_incomplete
                FROM Medicines WHERE medicine_id IN ({placeholders})""",
            ids,
        )
        rows = cursor.fetchall()
        for row in rows:
            row["product_count"] = counts.get(row["medicine_id"], 1)  # how common this variant is
        return rows
    finally:
        cursor.close()
        conn.close()


def _name_prefix_rows(cursor, prefix, limit=NAME_PREFIX_LIMIT):
    """
    Rows whose name starts with `prefix` - the ones where it is a WHOLE word
    taken first.

    Ordering only by name length buries the very product being looked for:
    "Pan-D" searched "pan%" and "Pan-D Capsule PR" lost all 25 slots to
    shorter, unrelated brands ("Pany Tablet", "Pansec Tablet"). A name that
    continues the word with another letter is a different brand; one that
    breaks at a separator is the same brand with a variant suffix, so those
    are collected first and the plain prefix only fills what is left.
    """
    rows = {}
    for pattern in (prefix + "-%", prefix + " %", prefix + "%"):
        cursor.execute(
            """SELECT medicine_id, medicine_name, composition, form, strength,
                      primary_salt, secondary_salt, manufacturer, pack_size,
                      price, is_discontinued, release_type, composition_incomplete
               FROM Medicines
               WHERE medicine_name LIKE %s
               ORDER BY CHAR_LENGTH(medicine_name)
               LIMIT %s""",
            (pattern, limit),
        )
        for row in cursor.fetchall():
            rows.setdefault(row["medicine_id"], row)
    return list(rows.values())


def search_by_name_prefix(words):
    """
    Looks up medicines whose name STARTS WITH one of the given words.

    FULLTEXT relevance is built for prose, not product catalogues: searching
    "Monte*" ranks thousands of generic Montelukast products above the actual
    brand "Montek LC Tablet" (2801st of 4945), so the brand a doctor actually
    wrote can never survive a sane LIMIT. This lookup guarantees that if the
    line names a real brand, that brand is among the candidates to be scored.

    When a word matches nothing literally, it is retried on a shortened
    stem. Without that, "Amoxicillin" retrieved NOTHING here (the dataset
    spells it "Amoxycillin"), the plain product never reached scoring, and
    the match fell to whatever combination product FULLTEXT happened to
    rank first. The stem still has to be a real prefix of the name, so this
    widens which candidates get CONSIDERED - the scoring rules decide, and
    they are unchanged.

    Returns [] for empty input. Never invents a result.
    """
    if not words:
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        seen = {}
        for word in words:
            rows = _name_prefix_rows(cursor, word)
            if not rows and len(word) > SPELLING_FALLBACK_PREFIX_LEN:
                # A 4-letter stem is a much coarser question than a full
                # brand name, so take a wider slice and let the scorer
                # discriminate. Ordering by name length alone would return
                # the 25 shortest "Amox..." brands and still bury the plain
                # "Amoxycillin 500mg Capsule" the query actually meant.
                rows = _name_prefix_rows(
                    cursor, word[:SPELLING_FALLBACK_PREFIX_LEN], STEM_FALLBACK_LIMIT
                )
            for row in rows:
                seen.setdefault(row["medicine_id"], row)
        return list(seen.values())
    finally:
        cursor.close()
        conn.close()


def search_medicines_for_picker(term, limit=20):
    """The products matching what was typed (see search_medicines_with_mode), without the fallback flag."""
    return search_medicines_with_mode(term, limit)[0]


def search_medicines_with_mode(term, limit=20):
    """
    Free-text lookup used by the manual "which medicine is this?" picker. Returns (rows, used_fallback).

    Every word typed has to match the product (its name, its ingredients, its strength or its release
    type), hyphens / dots / spaces are interchangeable ("Pan D" = "Pan-D" = "pan - D"), and results are
    ranked by relevance - see app/services/medicine_search.py. Rows carry the composition and release type
    so the person can tell products apart. This is a search only: it never confirms anything.

    Falls back to a shortened prefix when nothing matches literally, because
    the dataset uses Indian/British salt spellings: searching the standard
    "Amoxicillin" found NOTHING while the dataset's "Amoxycillin" returned
    thousands. A user typing the spelling they know would conclude the
    database was empty. `used_fallback` is True for those results: they are products whose
    names merely START like the typed text, not products that match it, and the caller must say so.
    """
    term = (term or "").strip()
    if len(term) < 2:
        return [], False

    parsed = medicine_search.parse_query(term)
    if not parsed["tokens"]:
        return [], False                           # only a dosage form was typed ("tablet"): nothing to look for
    rows = medicine_search.rank_rows(term, _search_candidates_for_picker(parsed), limit)
    if rows:
        return rows, False

    # e.g. "amoxicillin" -> "amox%", which reaches "Amoxycillin" too.
    stem = "".join(ch for ch in term if ch.isalpha())[:SPELLING_FALLBACK_PREFIX_LEN]
    if len(stem) < SPELLING_FALLBACK_PREFIX_LEN:
        return [], False
    rows = _search_medicines_prefix(stem, limit)
    return rows, bool(rows)


def _search_medicines_prefix(stem, limit):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT medicine_id, medicine_name, composition, form, strength,
                      primary_salt, manufacturer, pack_size, price, is_discontinued,
                      release_type, composition_incomplete
               FROM Medicines
               WHERE medicine_name LIKE %s OR primary_salt LIKE %s
               ORDER BY (medicine_name LIKE %s) DESC, CHAR_LENGTH(medicine_name)
               LIMIT %s""",
            (f"{stem}%", f"{stem}%", f"{stem}%", limit),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# How many candidate products to pull before ranking. The shortest names come first, so a brand typed exactly is
# never cut; a very common word ("calcium") is ranked over its first PICKER_CANDIDATE_LIMIT products.
PICKER_CANDIDATE_LIMIT = 4000


def _search_candidates_for_picker(parsed):
    """
    A cheap superset of the products that could match every word typed (each word somewhere in the name or the
    ingredients, in any spelling that counts as the same word). Exactness - whole words, strengths, release
    type - is decided afterwards by medicine_search.rank_rows.
    """
    clauses, params, in_name, order_params = [], [], [], []
    for token in parsed["tokens"]:
        if token in medicine_search.RELEASE_WORDS:
            clauses.append("(release_type = %s OR LOWER(medicine_name) LIKE %s)")
            params += [medicine_search.RELEASE_WORDS[token], f"%{token}%"]
            continue
        if len(token) < 2:
            continue  # one-letter words ("pan D") are judged as whole words in Python, not as a substring of everything
        alternatives = medicine_search.alternatives(token)
        clauses.append("(" + " OR ".join(["LOWER(medicine_name) LIKE %s OR LOWER(composition) LIKE %s"] * len(alternatives)) + ")")
        for alt in alternatives:
            params += [f"%{alt}%", f"%{alt}%"]
        in_name.append("(LOWER(medicine_name) LIKE %s)")
        order_params.append(f"%{token}%")
    if not clauses:
        return []
    # Products whose NAME carries the words typed come first, so a long, well-named brand is not cut off by the limit
    # in favour of short names that matched only through their ingredients.
    order_by = (f"({' + '.join(in_name)}) DESC, " if in_name else "") + "CHAR_LENGTH(medicine_name), medicine_id"
    params = params + order_params

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""SELECT medicine_id, medicine_name, composition, form, strength,
                       primary_salt, manufacturer, pack_size, price, is_discontinued,
                       release_type, composition_incomplete
                FROM Medicines
                WHERE {" AND ".join(clauses)}
                ORDER BY {order_by}
                LIMIT %s""",
            params + [PICKER_CANDIDATE_LIMIT],
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def update_prescription_medicine_match(pm_id, medicine_id, match_status="user_confirmed"):
    """
    Repoints one detected line at the medicine the USER says it is.
    Confidence is cleared: the stored number described how sure the fuzzy
    matcher was, and it no longer has any bearing on a human's answer.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE Prescription_Medicines
               SET medicine_id = %s, match_status = %s, match_confidence = NULL,
                   match_options = NULL
               WHERE pm_id = %s""",
            (medicine_id, match_status, pm_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def mark_prescription_medicine_unmatched(pm_id):
    """
    Records that a person reviewed this line and said it is not a medicine PharmaCompare can
    identify. The line keeps its OCR text, its match confidence and the candidates it was shown
    (so the decision can be reviewed later), but points at no product: it is never analysed or priced.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Prescription_Medicines SET medicine_id = NULL, match_status = %s WHERE pm_id = %s",
            (match_status.USER_UNMATCHED, pm_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def save_user_entered_details(pm_id, match_options_json, frequency, duration):
    """
    Records a medicine the person typed in for a line the dataset cannot identify. The line points at no product (it is never priced
    or analysed), keeps its OCR text and the look-alikes it was shown, and carries the typed name / strength / form in match_options and
    the typed schedule and duration in frequency and duration. Nothing else on the line changes.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE Prescription_Medicines
               SET medicine_id = NULL, match_status = %s, match_options = %s, frequency = %s, duration = %s
               WHERE pm_id = %s""",
            (match_status.USER_UNMATCHED, match_options_json, frequency, duration, pm_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def delete_prescription_medicine(pm_id):
    """
    Removes one detected line. Price_Comparison and Generic_Recommendations
    reference pm_id with ON DELETE CASCADE, so their rows go with it.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Prescription_Medicines WHERE pm_id = %s", (pm_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def get_prescription_medicine(pm_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM Prescription_Medicines WHERE pm_id = %s", (pm_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_medicine_by_id(medicine_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM Medicines WHERE medicine_id = %s", (medicine_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def save_prescription_medicine(prescription_id, medicine_id, raw_text, match_confidence, match_status,
                                dosage=None, frequency=None, duration=None, match_options=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO Prescription_Medicines
                   (prescription_id, medicine_id, dosage, frequency, duration,
                    raw_text, match_confidence, match_status, match_options)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (prescription_id, medicine_id, dosage, frequency, duration,
             raw_text, match_confidence, match_status,
             json.dumps(match_options) if match_options else None),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_prescription_medicines(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT pm.pm_id, pm.raw_text, pm.match_status, pm.match_confidence,
                      pm.dosage, pm.frequency, pm.duration, pm.match_options,
                      m.medicine_id, m.medicine_name, m.composition, m.form,
                      m.strength, m.manufacturer, m.price, m.is_discontinued,
                      m.primary_salt, m.secondary_salt, m.pack_size, m.release_type, m.composition_incomplete, m.imported_at
               FROM Prescription_Medicines pm
               LEFT JOIN Medicines m ON pm.medicine_id = m.medicine_id
               WHERE pm.prescription_id = %s
               ORDER BY pm.pm_id""",
            (prescription_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
