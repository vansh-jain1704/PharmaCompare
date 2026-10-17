from app.db import get_connection


def save_report(prescription_id, report_file):
    """
    Records a generated Smart Health Report. Regenerating replaces the
    previous record for the prescription, so the table reflects the report
    that actually exists on disk rather than every attempt ever made.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Smart_Health_Report WHERE prescription_id = %s", (prescription_id,))
        cursor.execute(
            "INSERT INTO Smart_Health_Report (prescription_id, report_file) VALUES (%s, %s)",
            (prescription_id, report_file),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_report(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM Smart_Health_Report WHERE prescription_id = %s ORDER BY report_id DESC LIMIT 1",
            (prescription_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
