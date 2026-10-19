"""
Writes frontend/tests/fixtures/handwritten.json: the real analysis payload (GET /api/prescriptions/<id>) for the handwritten prescription in
tests/test_handwritten_prescription.py, produced by the actual pipeline with the captured Vision output. A throw-away account is used and removed.

  backend\\venv\\Scripts\\python.exe -m tests.make_handwritten_fixture
"""
import io
import json
import os
import sys
from unittest import mock

from flask_jwt_extended import create_access_token

from tests import helpers
from tests.test_handwritten_prescription import HINDI_LINES, ocr, png_bytes

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "tests", "fixtures", "handwritten.json")


def main():
    app = helpers.get_app()
    client = app.test_client()
    accounts = helpers.TempAccounts()
    try:
        with app.app_context():
            uid = accounts.user(allergies=[])
            headers = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
        with mock.patch("app.routes.prescriptions.extract_text", return_value=ocr(HINDI_LINES)):
            up = client.post("/api/prescriptions/upload", headers=headers, data={"file": (io.BytesIO(png_bytes()), "p.png")}, content_type="multipart/form-data")
        pid = up.get_json()["prescription_id"]
        accounts.prescription_ids.append(pid)
        body = client.get(f"/api/prescriptions/{pid}", headers=headers).get_json()
        body["prescription"].pop("filename", None)
        body["prescription"]["user_id"] = 0
        with open(OUT, "w", encoding="utf8") as handle:
            json.dump(body, handle, ensure_ascii=False, indent=1, default=str)
        print("wrote", OUT, "-", len(body["detected_medicines"]), "lines,", len(body["notes"]), "notes")
    finally:
        with app.app_context():
            accounts.cleanup()


if __name__ == "__main__":
    sys.exit(main())
