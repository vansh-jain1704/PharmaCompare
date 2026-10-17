import json

from app.db import get_connection


def find_interaction(salt_a_norm, salt_b_norm):
    """
    Looks up a known interaction between two normalized (lowercased) salt
    names. Order-independent. Returns the Drug_Interactions row, or None
    if this exact pair has no record - callers must treat None as
    "unknown", never as "confirmed safe".
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT * FROM Drug_Interactions
               WHERE (drug_a_norm = %s AND drug_b_norm = %s)
                  OR (drug_a_norm = %s AND drug_b_norm = %s)
               LIMIT 1""",
            (salt_a_norm, salt_b_norm, salt_b_norm, salt_a_norm),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def is_salt_covered(salt_norm):
    """Whether DDInter tracks this substance at all (in either column)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM Drug_Interactions WHERE drug_a_norm = %s OR drug_b_norm = %s LIMIT 1",
            (salt_norm, salt_norm),
        )
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


def save_finding(prescription_id, issue_type, medicines_involved, severity, confidence,
                  explanation, recommendation, data_source):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO Safety_Findings
                   (prescription_id, issue_type, medicines_involved, severity,
                    confidence, explanation, recommendation, data_source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (prescription_id, issue_type, json.dumps(medicines_involved), severity,
             confidence, explanation, recommendation, data_source),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_findings(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM Safety_Findings WHERE prescription_id = %s ORDER BY finding_id",
            (prescription_id,),
        )
        rows = cursor.fetchall()
        for row in rows:
            if row.get("medicines_involved"):
                row["medicines_involved"] = json.loads(row["medicines_involved"])
        return rows
    finally:
        cursor.close()
        conn.close()


def clear_findings(prescription_id):
    """Used only when re-running analysis for the same prescription (not
    currently exposed via API, kept for future re-analysis support)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Safety_Findings WHERE prescription_id = %s", (prescription_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def save_analysis_summary(prescription_id, summary, risk_level):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO AI_Analysis (prescription_id, summary, risk_level) VALUES (%s, %s, %s)",
            (prescription_id, summary, risk_level),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_analysis_summary(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM AI_Analysis WHERE prescription_id = %s ORDER BY analysis_id DESC LIMIT 1",
            (prescription_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def lookup_interaction_data(salt_variants):
    """
    One round trip for everything the per-medicine safety summary needs about
    a set of (lowercased, normalised) salt names:

      pairs   - {frozenset({a, b}): severity} for every DDInter record
                between two salts of the set
      covered - the salts DDInter tracks at all (in either column)

    Doing this once per prescription replaces what would otherwise be a few
    queries per medicine pair on every page load.
    """
    variants = sorted({v for v in salt_variants if v})
    if not variants:
        return {}, set()
    marks = ", ".join(["%s"] * len(variants))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""SELECT drug_a_norm, drug_b_norm, severity FROM Drug_Interactions
                WHERE drug_a_norm IN ({marks}) AND drug_b_norm IN ({marks})""",
            variants + variants,
        )
        pairs = {frozenset((a, b)): severity for a, b, severity in cursor.fetchall()}
        cursor.execute(
            f"""SELECT drug_a_norm FROM Drug_Interactions WHERE drug_a_norm IN ({marks})
                UNION
                SELECT drug_b_norm FROM Drug_Interactions WHERE drug_b_norm IN ({marks})""",
            variants + variants,
        )
        covered = {row[0] for row in cursor.fetchall()}
        return pairs, covered
    finally:
        cursor.close()
        conn.close()
