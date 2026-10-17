"""Pure-function tests: no database needed."""
import unittest

from tests import helpers  # noqa: F401  (sets sys.path)
from app.services.composition import (
    canonical_number, composition_key, ingredient_numerators, is_composition_incomplete, split_ingredients,
)
from app.services.release_type import derive_release_type, detect_line_release


class ReleaseTypeDerivation(unittest.TestCase):
    def test_name_marker(self):
        self.assertEqual(derive_release_type("Glycomet 500 SR Tablet", "strip of 10 tablets", "Tablet"), "sr")
        self.assertEqual(derive_release_type("Metforan 500mg Tablet XR", "strip of 10 tablets", "Tablet"), "er")

    def test_pack_size_marker(self):
        self.assertEqual(derive_release_type("Allmet 500mg Tablet", "strip of 10 tablets SR", "Tablet"), "sr")

    def test_conventional_is_none(self):
        self.assertIsNone(derive_release_type("Dolo 650 Tablet", "strip of 15 tablets", "Tablet"))
        self.assertIsNone(derive_release_type("Telma 40 Tablet", "strip of 15 tablets", "Tablet"))

    def test_od_is_not_treated_as_modified(self):
        # "OD" means once daily, not once-daily release
        self.assertIsNone(derive_release_type("Amlong 5 OD Tablet", "strip of 10 tablets", "Tablet"))

    def test_liquid_name_marker_ignored(self):
        # name markers are only trusted on solid oral forms
        self.assertIsNone(derive_release_type("Something SR Syrup", "bottle of 100 ml", "Syrup"))

    def test_conflicting_markers_flagged_modified(self):
        self.assertEqual(derive_release_type("Foo SR Tablet", "strip of 10 tablets ER", "Tablet"), "modified")


class LineReleaseDetection(unittest.TestCase):
    def test_stated(self):
        for text, expected in [("Tab Metformin 500 SR", "sr"), ("Metformin 500 ER", "er"), ("Nifedipine 30 XL", "er"),
                               ("Metformin 500 S.R.", "sr"), ("Metformin 500 sustained release", "sr"),
                               ("Pan-D PR", "pr")]:
            self.assertEqual(detect_line_release(text), expected, text)

    def test_not_stated(self):
        for text in ("Tab Dolo 650", "Metformin 500", "Dr. R Mehta, MBBS MD", "Pantoprazole 40 mg", "", None):
            self.assertIsNone(detect_line_release(text), text)


class CompositionHelpers(unittest.TestCase):
    def test_canonical_number(self):
        self.assertEqual(canonical_number("500.0"), "500")
        self.assertEqual(canonical_number("12.5"), "12.5")

    def test_split_and_strengths(self):
        comp = "Amoxycillin  (500mg) + Clavulanic Acid (125mg)"
        self.assertEqual([n for n, _ in split_ingredients(comp)], ["amoxycillin", "clavulanic acid"])
        self.assertEqual(ingredient_numerators(comp), ["500", "125"])

    def test_syrup_volume_is_not_a_dose(self):
        self.assertEqual(ingredient_numerators("Paracetamol (250mg/5ml)"), ["250"])

    def test_composition_key_distinguishes_strengths_and_ingredients(self):
        a = composition_key("Amoxycillin  (500mg) + Clavulanic Acid (125mg)")
        self.assertEqual(a, composition_key("amoxycillin (500mg)+clavulanic acid (125mg)"))
        self.assertNotEqual(a, composition_key("Amoxycillin  (1000mg) + Clavulanic Acid (200mg)"))
        self.assertNotEqual(a, composition_key("Amoxycillin (500mg)"))

    def test_incomplete_composition_flag(self):
        # name shows three strengths, the stored composition only lists two
        self.assertTrue(is_composition_incomplete("Foo 100mg/325mg/250mg Tablet", "A (100mg) + B (325mg)"))
        # three listed => complete
        self.assertFalse(is_composition_incomplete("Foo 100mg/325mg/250mg Tablet", "A (100mg) + B (325mg) + C (250mg)"))
        # two strengths in the name, two ingredients => complete
        self.assertFalse(is_composition_incomplete("Zerodol-P Tablet", "Aceclofenac (100mg) + Paracetamol (325mg)"))
        self.assertFalse(is_composition_incomplete("Augmentin 625 Duo Tablet", "Amoxycillin (500mg) + Clavulanic Acid (125mg)"))
        self.assertFalse(is_composition_incomplete(None, None))


if __name__ == "__main__":
    unittest.main()
