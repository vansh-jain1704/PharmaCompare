from app.db import get_connection
from app.services import price_quality
from app.services.composition import composition_key


def _comparable_filter(primary_salt, secondary_salt, strength, form, release_type, composition):
    """
    The WHERE clause (and its parameters) that defines "the same medicine, a
    different product": see find_alternatives for what each condition is for.
    A price of zero is not a price, so such rows never take part.
    """
    clauses = ["primary_salt = %s"]
    params = [primary_salt]
    # secondary_salt may be NULL (single-salt medicines) - match NULL to NULL and
    # non-NULL to the same value, never a NULL-vs-non-NULL "match"
    if secondary_salt:
        clauses.append("secondary_salt = %s")
        params.append(secondary_salt)
    else:
        clauses.append("secondary_salt IS NULL")
    clauses += ["strength = %s", "form = %s", "is_discontinued = FALSE", "release_type <=> %s",
                "composition_incomplete = 0", "price > 0"]
    params += [strength, form, release_type]
    if composition:
        clauses.append("REPLACE(LOWER(composition), ' ', '') = %s")
        params.append(composition_key(composition))
    return " AND ".join(clauses), params


# How many candidates to read before ordering them by the real pack-quantity rule (see find_alternatives).
PACK_WINDOW = 80


def find_alternatives(primary_salt, secondary_salt, strength, form, exclude_medicine_id, limit=10,
                      release_type=None, composition=None, pack_quantity=None, pack_size=None):
    """
    Finds other products with the same composition (primary + secondary
    salt) and strength and dosage form - the only combination that counts
    as a genuine substitute, per the rule to compare only compatible
    medicines. Discontinued products are excluded here (they're not
    something to present as a usable alternative), sorted cheapest first.
    Never invents a match - an empty list just means none exist.

    Two further conditions, because primary salt + strength + form is not
    enough to make two products the same medicine:
      - release_type must match (NULL matches NULL): a sustained-release tablet
        and a conventional tablet share salt, strength and form ("Tablet").
      - products whose stored ingredient list is known to be truncated
        (composition_incomplete) are never offered, because their real
        ingredients are unknown;
      - when `composition` is given, the full ingredient list with every
        ingredient's strength must match (ignoring spacing and case). The
        `strength` column only holds the first ingredient's strength, so
        "Amoxycillin 500 + Clavulanic Acid 125" and "... 500 + Clavulanic Acid
        500" used to look identical.

    When `pack_quantity` is given, products sold in that same quantity come first
    (cheapest first), then the rest: only a same-quantity price is a fair saving, and
    without this the cheapest ten were almost always strips of a different size.

    The database can only order by a text pattern ("of 15"), which also matches "bottle of 15 ml" for a strip of 15 tablets and
    "vial of 1 Injection" (a count) for "vial of 1 ml Injection" (a volume). When the prescribed product's `pack_size` text is given,
    the nearest PACK_WINDOW candidates are therefore re-ordered here by the SAME rule the savings use
    (price_quality.same_pack_quantity: the quantity AND its kind), so a pack that is not really comparable never takes the
    place of one that is, and the list is in the order the savings rule would sort it.
    """
    where, params = _comparable_filter(primary_salt, secondary_salt, strength, form, release_type, composition)
    where += " AND medicine_id != %s"
    params.append(exclude_medicine_id)

    order = "price ASC"
    if pack_quantity:
        qty = int(pack_quantity) if float(pack_quantity).is_integer() else pack_quantity
        order = "(pack_size REGEXP %s) DESC, price ASC"
        params.append(f"of {qty}( |$)")
    params.append(PACK_WINDOW if pack_size else limit)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""SELECT medicine_id, medicine_name, manufacturer, primary_salt, secondary_salt,
                       strength, form, pack_size, price, is_discontinued, data_source, imported_at
                FROM Medicines
                WHERE {where}
                ORDER BY {order}
                LIMIT %s""",
            params,
        )
        rows = cursor.fetchall()
        if pack_size:
            rows.sort(key=lambda r: (not price_quality.same_pack_quantity(pack_size, r["pack_size"]), float(r["price"]), r["medicine_id"]))
            rows = rows[:limit]
        return rows
    finally:
        cursor.close()
        conn.close()


def get_group_prices(primary_salt, secondary_salt, strength, form, release_type=None, composition=None):
    """(price, pack_size) of every live, priced product comparable with this one - the
    population that defines what a "usual" price per unit is (see price_quality)."""
    where, params = _comparable_filter(primary_salt, secondary_salt, strength, form, release_type, composition)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT price, pack_size FROM Medicines WHERE {where}", params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def save_price_row(pm_id, medicine_id, row_type, price, price_per_unit, pack_size,
                    price_difference, savings_percent, is_discontinued, data_source, price_date):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO Price_Comparison
                   (pm_id, medicine_id, row_type, price, price_per_unit, pack_size,
                    price_difference, savings_percent, is_discontinued, data_source, price_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (pm_id, medicine_id, row_type, price, price_per_unit, pack_size,
             price_difference, savings_percent, is_discontinued, data_source, price_date),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_price_comparison(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT pc.*, pm.raw_text, pm.match_status,
                      m.medicine_name, m.manufacturer, m.strength, m.form,
                      m.primary_salt, m.secondary_salt, m.release_type, m.composition
               FROM Price_Comparison pc
               JOIN Prescription_Medicines pm ON pc.pm_id = pm.pm_id
               JOIN Medicines m ON pc.medicine_id = m.medicine_id
               WHERE pm.prescription_id = %s
               ORDER BY pc.pm_id, pc.row_type DESC, pc.price ASC""",
            (prescription_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def clear_price_comparison(prescription_id):
    """Used only when re-running comparison for the same prescription (not
    currently exposed via API, kept for future re-analysis support)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """DELETE pc FROM Price_Comparison pc
               JOIN Prescription_Medicines pm ON pc.pm_id = pm.pm_id
               WHERE pm.prescription_id = %s""",
            (prescription_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
