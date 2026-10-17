"""
Shared test fixtures. These tests talk to the REAL local MySQL database, so every
record a test creates (users, prescriptions) is removed again in tearDown, and the
suite never touches existing accounts. Run from the backend folder:

    venv\Scripts\python.exe -m unittest discover -s tests -v
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

_app = None


def get_app():
    global _app
    if _app is None:
        _app = create_app()
    return _app


class TempAccounts:
    """Creates throw-away users/prescriptions and deletes them again."""

    def __init__(self):
        self.user_ids = []
        self.prescription_ids = []

    def user(self, allergies=None):
        from app.models.user_model import create_user, set_user_allergies
        email = f"zz_unittest_{uuid.uuid4().hex[:10]}@example.invalid"
        uid = create_user("Unit Test", email, "", "not-a-real-hash")
        self.user_ids.append(uid)
        if allergies is not None:
            set_user_allergies(uid, allergies)
        return uid

    def prescription(self, user_id, name="unittest.png"):
        from app.models.prescription_model import create_prescription
        pid = create_prescription(user_id, "unittest_dummy.png", prescription_name=name, status="processed")
        self.prescription_ids.append(pid)
        return pid

    def line(self, pid, medicine_name=None, raw_text=None, status="matched", confidence=0.9, **kw):
        """Adds a detected line, bound to the first Medicines row called `medicine_name`."""
        from app.db import get_connection
        from app.models.medicine_model import save_prescription_medicine
        medicine_id = None
        if medicine_name:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT medicine_id FROM Medicines WHERE medicine_name = %s LIMIT 1", (medicine_name,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            assert row, f"{medicine_name!r} is not in the dataset"
            medicine_id = row[0]
        return save_prescription_medicine(pid, medicine_id, raw_text or medicine_name, confidence, status, **kw)

    def cleanup(self):
        from app.db import get_connection
        from app.models.prescription_model import delete_prescription
        for pid in self.prescription_ids:
            delete_prescription(pid)
        conn = get_connection()
        cur = conn.cursor()
        for uid in self.user_ids:
            cur.execute("DELETE FROM Users WHERE user_id = %s", (uid,))
        conn.commit()
        cur.close()
        conn.close()
        # The app writes uploads and report PDFs under the owner's folder; remove what the test caused.
        import shutil
        from app.config import Config
        for uid in self.user_ids:
            shutil.rmtree(os.path.join(Config.UPLOAD_FOLDER, str(uid)), ignore_errors=True)
            shutil.rmtree(os.path.join(Config.UPLOAD_FOLDER, "reports", str(uid)), ignore_errors=True)
