# -*- coding: utf-8 -*-
"""Тесты tools/sitegen/text.py: обрезка meta description.

Запуск из корня репозитория:  python -m unittest discover tools/tests
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sitegen.text import truncate  # noqa: E402


class TruncateTest(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(truncate("  Квартира  в Будве. ", 160), "Квартира в Будве.")

    def test_prefers_whole_sentence(self):
        text = ("Коммерческая недвижимость, Будванская ривьера. Цена по запросу. Конфиденциальный инвестиционный "
                "объект: подробности — после квалификации инвестора и NDA. GUREVIĆ, Будва.")
        out = truncate(text, 160)
        self.assertLessEqual(len(out), 160)
        self.assertTrue(out.endswith("NDA."))

    def test_cuts_tail_before_dash(self):
        text = ("Вилла в Добра Воде: 275 м², участок 117 м², 7 спален. Цена: €400 000. ID BR-25-001K. "
                "Параметры, расположение и запрос просмотра — агентство недвижимости GUREVIĆ, Будва.")
        out = truncate(text, 160)
        self.assertEqual(out, "Вилла в Добра Воде: 275 м², участок 117 м², 7 спален. Цена: €400 000. ID BR-25-001K. "
                              "Параметры, расположение и запрос просмотра.")

    def test_abbreviation_is_not_sentence_end(self):
        text = "Appartement à Bečići : 59 m², 1 chambre. Prix : 226 000 €. Réf. BD-26-001S. " + "x" * 120
        out = truncate(text, 160, min_sentence=60)
        self.assertFalse(out.endswith("Réf."))
        self.assertTrue(out.endswith("BD-26-001S."))

    def test_word_boundary_with_ellipsis(self):
        out = truncate("слово " * 60, 160)
        self.assertLessEqual(len(out), 160)
        self.assertTrue(out.endswith("слово…"))


if __name__ == "__main__":
    unittest.main()
