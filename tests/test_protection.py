import unittest

from backend.main import Term, protect_text, restore_text


class ProtectionTests(unittest.TestCase):
    def test_latex_is_restored_exactly(self):
        text = r"We optimize $\mathcal{L}=\sum_i w_i$ and report results in \cref{tab:main}."
        protected, replacements = protect_text(text, [], direction="en-zh")
        self.assertNotIn(r"$\mathcal{L}=\sum_i w_i$", protected)
        self.assertNotIn(r"\cref{tab:main}", protected)
        self.assertEqual(restore_text(protected, replacements), text)

    def test_locked_english_term_stays_english_during_translation(self):
        terms = [Term(english="Anisotropic Visibility Field", chinese="各向异性可见性场", type="locked")]
        text = "We construct an Anisotropic Visibility Field for exploration."
        protected, replacements = protect_text(text, terms, direction="en-zh")
        restored = restore_text(protected, replacements)
        self.assertNotIn("Anisotropic Visibility Field", protected)
        self.assertIn("Anisotropic Visibility Field", restored)

    def test_locked_chinese_term_maps_to_canonical_english(self):
        terms = [Term(english="Next-Best View", chinese="下一最佳视点", type="locked")]
        text = "我们选择下一最佳视点进行观测。"
        protected, replacements = protect_text(text, terms, direction="zh-en")
        restored = restore_text(protected, replacements)
        self.assertNotIn("下一最佳视点", protected)
        self.assertIn("Next-Best View", restored)
        self.assertNotIn("下一最佳视点", restored)

    def test_missing_placeholder_is_rejected(self):
        protected, replacements = protect_text(r"Value is $x^2$.", [], direction="en-zh")
        with self.assertRaises(ValueError):
            restore_text(protected.replace(replacements[0][0], ""), replacements)


if __name__ == "__main__":
    unittest.main()
