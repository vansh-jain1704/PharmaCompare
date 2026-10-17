"""
A fresh install (schema.sql + the importer) must produce the same Medicines table, with the
same derived values, as the live database that was migrated in place.

Everything happens in a scratch table (Medicines_schema_check) that is dropped afterwards;
the live Medicines table is only ever read.
"""
import itertools
import os
import re
import sys
import unittest

from tests import helpers

DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
SCRATCH = "Medicines_schema_check"
SAMPLE_ROWS = 500


class FreshInstallMatchesLiveSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.get_app()
        sys.path.insert(0, DATABASE_DIR)
        from app.db import get_connection
        cls.conn = get_connection()
        cls.cur = cls.conn.cursor(dictionary=True)
        cls.cur.execute(f"DROP TABLE IF EXISTS {SCRATCH}")
        with open(os.path.join(DATABASE_DIR, "schema.sql"), encoding="utf-8") as fh:
            schema = fh.read()
        match = re.search(r"CREATE TABLE IF NOT EXISTS Medicines \(.*?\) ENGINE=InnoDB[^;]*;", schema, re.DOTALL)
        assert match, "Medicines CREATE TABLE not found in schema.sql"
        cls.cur.execute(match.group(0).replace("IF NOT EXISTS Medicines", f"IF NOT EXISTS {SCRATCH}", 1))

    @classmethod
    def tearDownClass(cls):
        cls.cur.execute(f"DROP TABLE IF EXISTS {SCRATCH}")
        cls.conn.commit()
        cls.cur.close()
        cls.conn.close()

    def columns(self, table):
        self.cur.execute(
            """SELECT COLUMN_NAME name, COLUMN_TYPE type, IS_NULLABLE nullable, COLUMN_DEFAULT dflt
               FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION""",
            (table,),
        )
        return [(r["name"], r["type"], r["nullable"], str(r["dflt"]).strip("'").lower() if r["dflt"] is not None else None) for r in self.cur.fetchall()]

    def test_columns_match_the_migrated_live_table(self):
        live = {c[0]: c for c in self.columns("Medicines")}
        fresh = {c[0]: c for c in self.columns(SCRATCH)}
        self.assertEqual(set(fresh), set(live), "column names differ between a fresh install and the live database")
        for name in fresh:
            self.assertEqual(fresh[name][1:], live[name][1:], f"column {name} differs")
        for derived in ("release_type", "composition_incomplete"):
            self.assertIn(derived, fresh)

    def test_indexes_match(self):
        def indexes(table):
            self.cur.execute("SELECT INDEX_NAME n, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) c, INDEX_TYPE t "
                             "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s GROUP BY INDEX_NAME, INDEX_TYPE", (table,))
            return {(r["n"], r["c"], r["t"]) for r in self.cur.fetchall()}
        self.assertEqual(indexes(SCRATCH), indexes("Medicines"))

    def test_the_importer_derives_the_same_values_the_migration_stored(self):
        import import_medicines as importer
        rows = list(itertools.islice(importer.read_rows(), SAMPLE_ROWS))
        self.assertEqual(len(rows), SAMPLE_ROWS)
        self.cur.executemany(importer.INSERT_SQL.replace("INSERT INTO Medicines", f"INSERT INTO {SCRATCH}"), [tuple(r) for r in rows])
        self.conn.commit()
        self.cur.execute(f"SELECT COUNT(*) n FROM {SCRATCH}")
        self.assertEqual(self.cur.fetchone()["n"], SAMPLE_ROWS)

        ids = [r[10] for r in rows]  # source_dataset_id
        placeholders = ",".join(["%s"] * len(ids))
        self.cur.execute(f"""SELECT f.source_dataset_id id, f.release_type fr, f.composition_incomplete fc, f.medicine_name fn,
                                    l.release_type lr, l.composition_incomplete lc, l.medicine_name ln
                             FROM {SCRATCH} f JOIN Medicines l ON l.source_dataset_id = f.source_dataset_id AND l.medicine_name = f.medicine_name
                             WHERE f.source_dataset_id IN ({placeholders})""", ids)
        joined = self.cur.fetchall()
        self.assertGreaterEqual(len(joined), SAMPLE_ROWS)  # a source id can match more than one row, never fewer
        self.assertEqual([j for j in joined if (j["fr"], j["fc"]) != (j["lr"], j["lc"])], [])


if __name__ == "__main__":
    unittest.main()
