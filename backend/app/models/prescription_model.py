import json

from app.db import get_connection
from app.models import verification_log_model


def create_prescription(user_id, image_path, prescription_name=None, prescription_type=None,
                         symptoms=None, status="uploaded"):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO Prescriptions
                   (user_id, image_path, prescription_name, prescription_type, symptoms, status)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                user_id,
                image_path,
                prescription_name,
                prescription_type,
                json.dumps(symptoms) if symptoms is not None else None,
                status,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def update_prescription_status(prescription_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Prescriptions SET status = %s WHERE prescription_id = %s",
            (status, prescription_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_prescription(prescription_id):
    """
    Deletes a Prescriptions row. Every child table (OCR_Results,
    Prescription_Medicines, AI_Analysis, Safety_Findings,
    Price_Comparison, Generic_Recommendations, Smart_Health_Report)
    already has ON DELETE CASCADE in schema.sql, so this one delete
    cleans up everything - no schema change, no new tables.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # the review trail of this prescription's medicine verifications goes with it (System_Logs has no
        # foreign key to a prescription, so it would otherwise outlive it)
        verification_log_model.delete_decisions(prescription_id, cursor)
        cursor.execute("DELETE FROM Prescriptions WHERE prescription_id = %s", (prescription_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def _decode_symptoms(row):
    if row and row.get("symptoms"):
        # mysql-connector-python returns JSON columns as raw text; decode
        # so API consumers get a real object, not a JSON string nested
        # inside JSON.
        row["symptoms"] = json.loads(row["symptoms"])
    return row


def get_prescription_by_id(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM Prescriptions WHERE prescription_id = %s",
            (prescription_id,),
        )
        return _decode_symptoms(cursor.fetchone())
    finally:
        cursor.close()
        conn.close()


def list_prescriptions_by_user(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM Prescriptions WHERE user_id = %s ORDER BY upload_date DESC",
            (user_id,),
        )
        return [_decode_symptoms(row) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def save_ocr_result(prescription_id, extracted_text, confidence_score, lines=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO OCR_Results (prescription_id, extracted_text, line_results, confidence_score)
               VALUES (%s, %s, %s, %s)""",
            (prescription_id, extracted_text, json.dumps(lines) if lines is not None else None, confidence_score),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_ocr_result_by_prescription(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM OCR_Results WHERE prescription_id = %s",
            (prescription_id,),
        )
        result = cursor.fetchone()
        if result and result.get("line_results"):
            # mysql-connector-python returns JSON columns as raw text;
            # decode it here so API consumers get real objects, not a
            # JSON string nested inside JSON.
            result["line_results"] = json.loads(result["line_results"])
        return result
    finally:
        cursor.close()
        conn.close()
