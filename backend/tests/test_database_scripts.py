"""The migration is idempotent and neither script deletes or alters existing data."""
import os
import subprocess
import sys
import unittest

from tests import helpers

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(script, *args):
    result = subprocess.run([sys.executable, os.path.join("database", script), *args], cwd=BACKEND,
                            capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, result.stderr
    return result.stdout


class DatabaseScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.get_app()

    def _fingerprint(self):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*), SUM(price), SUM(CRC32(medicine_name)), SUM(CRC32(IFNULL(composition,''))),
                              SUM(CRC32(IFNULL(strength,''))), SUM(composition_incomplete) FROM Medicines""")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row

    def test_migration_is_idempotent_and_non_destructive(self):
        before = self._fingerprint()
        out = _run("migrate_derived_columns.py")
        self.assertIn("derived columns written on 0 rows", out)
        self.assertEqual(self._fingerprint(), before)
        self.assertEqual(before[0], 253973)

    def test_audit_script_is_read_only(self):
        before = self._fingerprint()
        out = _run("audit_dataset.py")
        self.assertIn("MEDICINES TABLE", out)
        self.assertEqual(self._fingerprint(), before)

    def test_schema_and_importer_know_the_derived_columns(self):
        for fname in ("schema.sql", "import_medicines.py"):
            with open(os.path.join(BACKEND, "database", fname), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("composition_incomplete", text, fname)
            self.assertIn("release_type", text, fname)


if __name__ == "__main__":
    unittest.main()
