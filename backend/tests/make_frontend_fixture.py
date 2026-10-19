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
    "Cap Omez 20",               # matched to a tablet although the line says capsule: "Check match"
    "T Lincont 100",             # only look-alikes; the person then confirms Zincold Syrup despite the differences
    "T Linogen XT",              # only look-alikes; the person then marks it "not identified"
    "Tab Zincovit",              # only look-alikes, left for the person to review
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
            # the person's decisions, made through the real routes (so the review trail and the re-analysis are real too)
            from app.models.medicine_model import get_prescription_medicines
            client = app.test_client()
            by_text = {m["raw_text"]: m["pm_id"] for m in get_prescription_medicines(pid)}
            from app.db import get_connection
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT medicine_id FROM Medicines WHERE medicine_name = 'Zincold Syrup' LIMIT 1")
            zincold = cur.fetchone()[0]
            cur.close()
            conn.close()
            r = client.patch(f"/api/prescriptions/{pid}/medicines/{by_text['T Lincont 100']}",
                             json={"medicine_id": zincold, "acknowledge_warnings": True}, headers=headers)
            assert r.status_code == 200, r.get_json()
            r = client.post(f"/api/prescriptions/{pid}/medicines/{by_text['T Linogen XT']}/unmatched", headers=headers)
            assert r.status_code == 200, r.get_json()
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
                            "form_conflict": ln["safety"]["form_conflict"],
                            "confirmed_with_conflicts": ln["safety"]["confirmed_with_conflicts"],
                            "reason": ln["reason"],
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
