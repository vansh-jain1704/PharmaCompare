from app.db import get_connection


def save_recommendation(pm_id, recommended_medicine_id, generic_name, price_difference,
                         confidence_score, reason, data_source):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO Generic_Recommendations
                   (pm_id, recommended_medicine_id, generic_name, price_difference,
                    confidence_score, reason, data_source)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (pm_id, recommended_medicine_id, generic_name, price_difference,
             confidence_score, reason, data_source),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def clear_recommendations(prescription_id):
    """
    Drops this prescription's recommendations so they can be regenerated -
    needed when a user corrects a detected medicine, since every downstream
    result was derived from the medicine that was replaced.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """DELETE gr FROM Generic_Recommendations gr
               JOIN Prescription_Medicines pm ON gr.pm_id = pm.pm_id
               WHERE pm.prescription_id = %s""",
            (prescription_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_recommendations(prescription_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT gr.*, pm.raw_text
               FROM Generic_Recommendations gr
               JOIN Prescription_Medicines pm ON gr.pm_id = pm.pm_id
               WHERE pm.prescription_id = %s
               ORDER BY gr.pm_id, gr.confidence_score DESC, gr.price_difference ASC""",
            (prescription_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
