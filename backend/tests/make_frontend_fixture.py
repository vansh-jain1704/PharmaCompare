"""
Regenerates frontend/tests/fixtures/analysis.json from a REAL backend run, so the
frontend logic tests compare the UI's rules with real API output and with the numbers
the PDF is built from. Not a unit test (the name does not match test_*.py); run it
from the backend folder whenever the API shape changes:

    venv\\Scripts\\python.exe tests\\make_frontend_fixture.py

It uses a throw-away account and removes everything it creates. The fixture holds
medicine names and prices from the public dataset only: no patient data.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import helpers  # noqa: E402

LINES = [
    "Tab Dolo 650",              # a brand, but the OCR was unsure of this line: "Check match", no saving
    "Tab Paracetamol 650",       # generic name: matched, brand not named, no saving
    "Metformin",                 # under-specified: candidates, no product named
    "Tab Metformin 500 SR",      # sustained release stated
    "Tab Augmentin 625 Duo",     # allergy alert (penicillin)
    "Tab Telma 40",              # strips of 30: different-pack alternatives are not savings
    "Nifedipine 30",             # unsupported strength: unidentified, no candidates
    "Augmentin",                 # brand with several strengths/forms: candidates
]


def main():
    app = helpers.get_app()
    with app.app_context():
        from flask_jwt_extended import create_access_token
        from app.models.prescription_model import get_prescription_by_id
        from app.routes.prescriptions import _rerun_analysis, _run_medicine_detection
        from app.services.smart_report_service import collect_report_data

        accounts = helpers.TempAccounts()
        try:
            uid = accounts.user(allergies=["Penicillin"])
            pid = accounts.prescription(uid)
            from app.models.prescription_model import save_ocr_result
            save_ocr_result(pid, "\n".join(LINES), 0.8, lines=[
                {"text": t, "confidence": 0.4 if t == "Tab Dolo 650" else 0.97, "uncertain": t == "Tab Dolo 650"} for t in LINES
            ])
            _run_medicine_detection(pid, [{"text": t} for t in LINES])
            _rerun_analysis(pid)
            headers = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
            detail = app.test_client().get(f"/api/prescriptions/{pid}", headers=headers).get_json()
            data = collect_report_data(pid, get_prescription_by_id(pid))
            fixture = {
                "detail": detail,
                "pdf": {
                    "total_saving": data["total_saving"],
                    "counted_for_savings": data["counted_for_savings"],
                    "lines": [
                        {
                            "raw_text": ln["pm"]["raw_text"],
                            "status": ln["status"],
                            "confidence": ln["confidence"],
                            "saving": ln["saving"],
                            "price": ln["price"],
                            "allergy_alert": ln["safety"]["allergy_alert"],
                            "ocr_uncertain": ln["safety"]["ocr_uncertain"],
                            "release_label": ln["safety"]["release_label"],
                            "brand_unspecified": ln["safety"]["brand_unspecified"],
                            "composition": ln["pm"].get("composition"),
                        }
                        for ln in data["lines"]
                    ],
                },
            }
            for volatile in ("prescription", "ocr_result"):
                fixture["detail"].pop(volatile, None)
            out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               "frontend", "tests", "fixtures", "analysis.json")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(fixture, fh, indent=1, default=str)
            print("wrote", out, "-", len(data["lines"]), "lines")
        finally:
            accounts.cleanup()


if __name__ == "__main__":
    main()
