# -*- coding: utf-8 -*-
"""Тесты tools/notion_sync.py (офлайн, на фикстурах tools/tests/fixtures/*.json).

Запуск из корня репозитория:  python -m unittest discover tools/tests
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
SALES = os.path.join(FIXTURES, "sales_pages.json")
RENT = os.path.join(FIXTURES, "rent_pages.json")
sys.path.insert(0, TOOLS)

import notion_sync as ns  # noqa: E402

# Значения приватных колонок в фикстурах помечены маркером PRIVATE-…
PRIVATE_MARKERS = ("PRIVATE", "+382 67", "Provizija", "Owner", "dropbox.com", "3.5")


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def offline_ctx(root=None):
    return ns.SyncContext(offline=True, root=root or tempfile.gettempdir())


def build_sales():
    return quiet(ns.build_sales, ns.load_fixture(SALES), offline_ctx())


def build_rentals():
    return quiet(ns.build_rentals, ns.load_fixture(RENT), offline_ctx())


def by_object_id(items):
    return {x["objectId"]: x for x in items}


def page(props, pid="00000000-0000-0000-0000-0000000000ff"):
    """Мини-страница Notion для точечных тестов."""
    out = {}
    for name, value in props.items():
        if isinstance(value, tuple):           # ("select", "Villa") / ("number", 5) …
            kind, v = value
            if kind == "select":
                out[name] = {"type": "select", "select": {"name": v} if v else None}
            elif kind == "status":
                out[name] = {"type": "status", "status": {"name": v}}
            elif kind == "multi":
                out[name] = {"type": "multi_select", "multi_select": [{"name": x} for x in v]}
            elif kind == "number":
                out[name] = {"type": "number", "number": v}
            elif kind == "title":
                out[name] = {"type": "title", "title": [{"plain_text": v}]}
            elif kind == "checkbox":
                out[name] = {"type": "checkbox", "checkbox": v}
            elif kind == "date":
                out[name] = {"type": "date", "date": {"start": v}}
        else:
            out[name] = {"type": "rich_text", "rich_text": [{"plain_text": value}]}
    return {"id": pid, "properties": out}


class DistrictTests(unittest.TestCase):
    def test_canonical_table_matches(self):
        cases = {
            "Mediteranska bb, Bečići, Budva": "becici",
            "Boreti, Budva": "becici",
            "Rozino, Budva": "budva-rozino",
            "Slovenska obala 10, Budva": "budva-waterfront",
            "Šetalište Pet Danica, Herceg Novi": "herceg-novi",   # не набережная Будвы
            "Ivanica": "budva-ivanica",
            "Veligrad, Budva": "budva-veligrad",
            "Rafailovići, Budva": "rafailovici",
            "Pržno": "przno",
            "Sveti Stefan": "sveti-stefan",
            "Sv. Stefan, Budva": "sveti-stefan",
            "Lapčići": "lapcici",
            "Put za Tudoroviće": "tudorovici",
            "u Lastvi Grbaljskoj, Kotor": "lastva-grbaljska",
            "Lustve Grbaljskoj": "lastva-grbaljska",
            "Buljarica, Petrovac": "buljarica",
            "Petrovac na moru": "petrovac",
            "Tivat, Porto": "tivat",
            "Kotor, Dobrota": "kotor",
            "Kotorska 5, Budva": "budva-center",     # улица в Будве, не город Котор
            "Herceg-Novi": "herceg-novi",
            "Šušanj, Bar": "bar",
            "Barok residence, Budva": "budva-center",  # «Barok» не город Бар
            "Dobra Voda, Bar": "dobra-voda",
            "Ulcinj": "ulcinj",
            "Kuća preko rijeke Crnojrvića": "rijeka-crnojevica",
            "Cetinje": "cetinje",
            "Obzovica": "cetinje",
            "Podgorica, Zabjelo": "podgorica",
            "Budva": "budva-center",
            "Квартира в Бечичи": "becici",
            "Ulica bez grada 7": "other",
            "": "other",
        }
        for text, key in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ns.detect_district(text), key)

    def test_location_has_priority_over_title(self):
        self.assertEqual(ns.detect_district("Rozino, Budva", "Vila Bečići"), "budva-rozino")
        self.assertEqual(ns.detect_district(None, "Vila Bečići"), "becici")

    def test_fallback_is_not_budva_center(self):
        self.assertEqual(ns.district_label(ns.detect_district("nowhere")), "Черногория")

    def test_select_override(self):
        self.assertEqual(ns.district_from_select("Bečići"), "becici")
        self.assertEqual(ns.district_from_select("Budva – centre"), "budva-center")
        self.assertEqual(ns.district_from_select("Herceg Novi"), "herceg-novi")
        self.assertEqual(ns.district_from_select("sveti-stefan"), "sveti-stefan")
        self.assertIsNone(ns.district_from_select(None))
        self.assertIsNone(ns.district_from_select("Atlantis"))

    def test_table_covers_brief_keys(self):
        keys = [d[0] for d in ns.DISTRICTS]
        self.assertEqual(keys[-2:], ["budva-center", "other"])
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 24)


class SalesMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = build_sales()
        cls.by_id = by_object_id(cls.items)

    def test_only_available_published(self):
        self.assertNotIn("BD-26-008S", self.by_id)          # Sold
        self.assertEqual(len(self.items), 10)                # 12 страниц − Sold − юнит проекта

    def test_apartment_public_buy(self):
        a = self.by_id["BD-26-001S"]
        self.assertEqual((a["kind"], a["type"], a["section"], a["disclosure"]),
                         ("apartment", "apartment", "buy", "public"))
        self.assertEqual((a["districtKey"], a["location"]), ("becici", "Бечичи"))
        # название CRM не-проекта не публикуется (в нём бывают имена владельцев)
        self.assertIsNone(a["crmTitle"])
        self.assertEqual(a["title"], "Квартира 68 м² — Бечичи")
        self.assertNotIn("Apartman sa pogledom", json.dumps(a, ensure_ascii=False))
        self.assertEqual(a["bedrooms"], 2)
        self.assertEqual(a["rooms"], "2 спальни")
        self.assertEqual(a["coords"], [42.2831, 18.8702])
        self.assertEqual(a["features"], ["Вид на море", "Бассейн"])
        self.assertEqual(a["id"], "bd-26-001s")

    def test_texts_by_language(self):
        a = self.by_id["BD-26-001S"]
        self.assertEqual(set(a["texts"]), {"card", "description", "location"})
        self.assertEqual(set(a["texts"]["card"]), {"ru", "en"})
        self.assertTrue(a["texts"]["card"]["en"].startswith("Bright"))
        self.assertEqual(set(a["texts"]["location"]), {"ru"})
        villa = self.by_id["BD-26-002S"]
        self.assertEqual(villa["texts"]["card"], {"de": "Villa mit Pool und Meerblick."})

    def test_contacts_scrubbed_from_texts(self):
        a = self.by_id["BD-26-001S"]
        blob = json.dumps(a, ensure_ascii=False)
        self.assertNotIn("111 222", blob)
        self.assertNotIn("@example.com", blob)

    def test_villa_kind_and_legacy_type(self):
        v = self.by_id["BD-26-002S"]
        self.assertEqual((v["kind"], v["type"], v["section"]), ("villa", "house", "buy"))
        self.assertEqual(v["districtKey"], "tudorovici")

    def test_confidential_hotel_is_anonymized(self):
        h = self.by_id["BD-26-003S"]
        self.assertEqual((h["kind"], h["section"], h["disclosure"]), ("hotel", "invest", "confidential"))
        self.assertEqual(h["title"], "Отель, Будва")
        self.assertIsNone(h["crmTitle"])
        for key in ("images", "coords", "projectName"):
            self.assertNotIn(key, h)
        self.assertEqual(h["photos"], 0)
        blob = json.dumps(h, ensure_ascii=False)
        self.assertNotIn("Aurora", blob)
        self.assertTrue(h["invest"])
        self.assertEqual(h["price"], 16000000)

    def test_gradnja_is_public_development_with_units(self):
        g = self.by_id["RF-26-004G"]
        self.assertEqual((g["kind"], g["section"], g["disclosure"]), ("development", "invest", "public"))
        self.assertTrue(g["isComplex"])
        self.assertEqual(g["price"], 0)
        self.assertEqual(g["priceNote"], "Цена по запросу")
        self.assertEqual(len(g["units"]), 1)
        self.assertEqual(g["units"][0]["unitCode"], "A-12")
        self.assertEqual(g["units"][0]["bedrooms"], 1)
        self.assertNotIn("RF-26-005A", self.by_id)

    def test_section_override_land_invest_confidential(self):
        land = self.by_id["BD-26-006S"]
        self.assertEqual((land["kind"], land["section"], land["disclosure"]),
                         ("land", "invest", "confidential"))
        self.assertEqual(land["districtKey"], "buljarica")

    def test_disclosure_override_public_warehouse(self):
        w = self.by_id["BD-26-007S"]
        self.assertEqual((w["kind"], w["section"], w["disclosure"]), ("commercial", "invest", "public"))
        self.assertIsNone(w["crmTitle"])
        self.assertEqual(w["title"], "Коммерческое помещение 2400 м² — Подгорица")
        self.assertNotIn("Skladište", json.dumps(w, ensure_ascii=False))

    def test_development_keeps_crm_title(self):
        g = self.by_id["RF-26-004G"]
        self.assertEqual(g["crmTitle"], "Residence Lux Rafailovići")
        self.assertEqual(g["title"], "Residence Lux Rafailovići")

    def test_no_crm_title_outside_development(self):
        for item in self.items:
            if item["kind"] != "development":
                self.assertIsNone(item["crmTitle"], item["id"])

    def test_district_select_overrides_address(self):
        b = self.by_id["BD-26-009S"]
        self.assertEqual(b["districtKey"], "herceg-novi")
        self.assertEqual((b["kind"], b["disclosure"]), ("business", "confidential"))
        self.assertEqual(b["title"], "Готовый бизнес, Херцег-Нови")

    def test_autotitle_and_fallback_district(self):
        x = self.by_id["BD-26-010S"]
        self.assertIsNone(x["crmTitle"])
        self.assertEqual(x["title"], "Квартира 35 м² — Черногория")
        self.assertEqual(x["districtKey"], "other")

    def test_every_listing_has_new_keys(self):
        for item in self.items:
            for key in ("crmTitle", "kind", "section", "disclosure", "districtKey", "texts",
                        "id", "title", "type", "deal", "location", "price", "hue", "photos"):
                self.assertIn(key, item, f"{item['id']} без {key}")
            self.assertIn(item["section"], ("buy", "invest", "rent"))
            self.assertIn(item["disclosure"], ("public", "confidential"))

    def test_hue_is_stable(self):
        again = by_object_id(build_sales())
        for oid, item in self.by_id.items():
            self.assertEqual(item["hue"], again[oid]["hue"])


class DefaultsTests(unittest.TestCase):
    def test_kind_mapping(self):
        cases = {"Apartment": "apartment", "House": "house", "Villa": "villa", "Land": "land",
                 "Hotel": "hotel", "Commercial": "commercial", "Office": "commercial",
                 "Retail": "commercial", "Industrial": "commercial", "Warehouse": "commercial",
                 "Business": "business", "Gradnja": "development"}
        for value, kind in cases.items():
            with self.subTest(value=value):
                self.assertEqual(ns.kind_from_type(value), kind)

    def test_disclosure_defaults(self):
        self.assertEqual(ns.default_disclosure("development", "invest"), "public")
        for kind in ("hotel", "commercial", "business"):
            self.assertEqual(ns.default_disclosure(kind, "invest"), "confidential")
        self.assertEqual(ns.default_disclosure("land", "invest"), "confidential")
        self.assertEqual(ns.default_disclosure("land", "buy"), "public")
        for kind in ("apartment", "house", "villa"):
            self.assertEqual(ns.default_disclosure(kind, "buy"), "public")

    def test_section_defaults_and_parsing(self):
        for kind in ("apartment", "house", "villa", "land"):
            self.assertEqual(ns.default_section(kind), "buy")
        for kind in ("hotel", "commercial", "business", "development"):
            self.assertEqual(ns.default_section(kind), "invest")
        self.assertEqual(ns.parse_section("Invest"), "invest")
        self.assertEqual(ns.parse_section("Buy"), "buy")
        self.assertIsNone(ns.parse_section(""))
        self.assertEqual(ns.parse_disclosure("Confidential"), "confidential")
        self.assertEqual(ns.parse_disclosure("Public"), "public")

    def test_website_section_buy_overrides_hotel_default(self):
        p = page({"Status": ("status", "Available"), "Property Type": ("select", "Hotel"),
                  "Website Section": ("select", "Buy"), "Object ID": "X-1", "Location": "Budva"})
        item = quiet(ns.page_to_listing, p, offline_ctx())
        self.assertEqual(item["section"], "buy")
        self.assertEqual(item["disclosure"], "confidential")   # hotel остаётся конфиденциальным

    def test_rent_deal_in_sales_db_not_in_buy(self):
        p = page({"Status": ("status", "Available"), "Property Type": ("select", "Apartment"),
                  "Deal Type": ("select", "Rent"), "Cijena": ("number", 800), "Object ID": "X-2"})
        item = quiet(ns.page_to_listing, p, offline_ctx())
        self.assertEqual((item["section"], item["deal"], item["monthlyPrice"]), ("rent", "rent", 800))


class RentalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = build_rentals()
        cls.by_id = by_object_id(cls.items)

    def test_only_available_long_term(self):
        self.assertEqual(sorted(self.by_id), ["RN-26-001", "RN-26-002"])  # без Rented и посуточной

    def test_rent_keys(self):
        r = self.by_id["RN-26-001"]
        self.assertEqual((r["section"], r["deal"], r["disclosure"]), ("rent", "rent", "public"))
        self.assertEqual(r["monthlyPrice"], 900)
        self.assertEqual(r["price"], 900)
        self.assertEqual(r["rentalTerms"], ["off_season", "year"])
        self.assertEqual(r["deposit"], 900)
        self.assertEqual(r["availableFrom"], "2026-11-01")
        self.assertEqual(r["minTermMonths"], 6)
        self.assertEqual(r["utilities"], "not_included")
        self.assertEqual(r["pets"], "by_agreement")
        self.assertEqual(r["districtKey"], "budva-rozino")
        self.assertEqual(set(r["texts"]["card"]), {"ru", "en", "uk"})
        self.assertNotIn("priceNote", r)

    def test_villa_rental(self):
        v = self.by_id["RN-26-002"]
        self.assertEqual((v["kind"], v["type"]), ("villa", "house"))
        self.assertEqual((v["utilities"], v["pets"]), ("included", "allowed"))
        self.assertEqual(v["districtKey"], "lastva-grbaljska")

    def test_term_and_option_parsing(self):
        self.assertEqual(ns.parse_rental_terms(["Year", "Off-season"]), ["off_season", "year"])
        self.assertEqual(ns.parse_rental_terms(["До начала сезона", "На год"]), ["off_season", "year"])
        self.assertEqual(ns.parse_rental_terms("Short-term"), ["short_term"])
        self.assertEqual(ns.parse_utilities("Partly included"), "partial")
        self.assertEqual(ns.parse_utilities("Не включены"), "not_included")
        self.assertEqual(ns.parse_pets(True), "allowed")
        self.assertEqual(ns.parse_pets("Not allowed"), "not_allowed")
        self.assertIsNone(ns.parse_pets(None))

    def test_monthly_rent_falls_back_to_cijena(self):
        p = page({"Status": ("status", "Available"), "Property Type": ("select", "Apartment"),
                  "Cijena": ("number", 650), "Rental Term": ("multi", ["Year"]), "Object ID": "R-9"})
        item = quiet(ns.page_to_rental, p, offline_ctx())
        self.assertEqual(item["monthlyPrice"], 650)


class PrivacyTests(unittest.TestCase):
    def test_private_columns_never_in_output(self):
        text = ns.render_js(build_sales(), "LISTINGS") + ns.render_js(build_rentals(), "RENTALS")
        for marker in PRIVATE_MARKERS:
            self.assertNotIn(marker, text, f"утечка: {marker}")
        self.assertNotIn("Mediteranska", text)   # точный адрес
        self.assertNotIn("PRIVATE-STREET", text)

    def test_field_maps_have_no_private_columns(self):
        private = {"owner name", "owner phone", "provizija", "list nep.", "documents folder",
                   "person", "cadastral municipality"}
        for fmap in (ns.FIELD_MAP, ns.FIELD_MAP_RENT):
            for names in fmap.values():
                for name in (names,) if isinstance(names, str) else names:
                    self.assertNotIn((name or "").lower(), private)

    def test_scrub_contacts(self):
        self.assertEqual(ns.scrub_contacts("Тел. +382 69 572 257, mail a.b@c.me."), "Тел., mail.")
        self.assertEqual(ns.scrub_contacts("Звоните 069 123 456"), "Звоните")
        self.assertEqual(ns.scrub_contacts("Цена 350 000 €, 120 м²"), "Цена 350 000 €, 120 м²")


class CliAndFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="notion-sync-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        for key in ns.SECRET_KEYS:
            env.pop(key, None)
        return subprocess.run([sys.executable, os.path.join(TOOLS, "notion_sync.py"), *args],
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

    def test_fixture_dry_run_writes_nothing(self):
        res = self.run_cli("--fixture", SALES, "--dry-run", "--out-dir", self.tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("const LISTINGS", res.stdout)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_fixture_writes_both_files(self):
        res = self.run_cli("--fixture", SALES, "--rent-fixture", RENT, "--out-dir", self.tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        sales = ns.read_js_array(os.path.join(self.tmp, "data.js"))
        rentals = ns.read_js_array(os.path.join(self.tmp, "rentals.js"))
        self.assertEqual((len(sales), len(rentals)), (10, 2))
        with open(os.path.join(self.tmp, "rentals.js"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("// ===="))
        self.assertIn("const RENTALS =\n[", text)
        self.assertTrue(text.endswith("];\n"))

    def test_missing_rent_db_creates_empty_or_keeps_existing(self):
        rent_path = os.path.join(self.tmp, "rentals.js")
        self.run_cli("--fixture", SALES, "--out-dir", self.tmp)
        self.assertEqual(ns.read_js_array(rent_path), [])
        with open(rent_path, "w", encoding="utf-8") as fh:
            fh.write('const RENTALS =\n[{"id": "keep-me"}];\n')
        self.run_cli("--fixture", SALES, "--out-dir", self.tmp)
        self.assertEqual(ns.read_js_array(rent_path), [{"id": "keep-me"}])

    def test_previous_images_are_kept(self):
        img_dir = os.path.join(self.tmp, "img", "listings", "bd-26-001s")
        os.makedirs(img_dir)
        open(os.path.join(img_dir, "01.jpg"), "wb").close()
        ctx = ns.SyncContext(offline=True, root=self.tmp, previous={
            "bd-26-001s": {"images": ["img/listings/bd-26-001s/01.jpg", "img/listings/bd-26-001s/gone.jpg"]},
            "bd-26-003s": {"images": ["img/listings/bd-26-001s/01.jpg"], "coords": [1, 2]},
        })
        items = by_object_id(quiet(ns.build_sales, ns.load_fixture(SALES), ctx))
        self.assertEqual(items["BD-26-001S"]["images"], ["img/listings/bd-26-001s/01.jpg"])
        self.assertEqual(items["BD-26-001S"]["photos"], 1)
        self.assertNotIn("images", items["BD-26-003S"])   # конфиденциальный — без фото
        self.assertNotIn("coords", items["BD-26-003S"])

    def test_sanitize_after_dropbox(self):
        data_path = os.path.join(self.tmp, "data.js")
        listings = build_sales()
        hotel = by_object_id(listings)["BD-26-003S"]
        hotel["images"] = ["img/listings/bd-26-003s/01.jpg"]   # как будто дописал dropbox_sync
        hotel["coords"] = [42.29, 18.848]
        with open(data_path, "w", encoding="utf-8") as fh:
            fh.write(ns.render_js(listings))
        folder = os.path.join(self.tmp, "img", "listings", "bd-26-003s")
        os.makedirs(folder)
        open(os.path.join(folder, "01.jpg"), "wb").close()
        changed = quiet(ns.sanitize_file, data_path, root=self.tmp)
        self.assertEqual(changed, 1)
        self.assertFalse(os.path.exists(folder))
        hotel2 = by_object_id(ns.read_js_array(data_path))["BD-26-003S"]
        self.assertNotIn("images", hotel2)
        self.assertNotIn("coords", hotel2)

    def test_sanitize_strips_private_crm_titles(self):
        data_path = os.path.join(self.tmp, "data.js")
        listings = build_sales()
        items = by_object_id(listings)
        items["BD-26-001S"]["crmTitle"] = items["BD-26-001S"]["title"] = "Stan od Aleksandra u Bečićima"
        with open(data_path, "w", encoding="utf-8") as fh:
            fh.write(ns.render_js(listings))
        changed = quiet(ns.sanitize_file, data_path, root=self.tmp)
        self.assertEqual(changed, 1)
        after = by_object_id(ns.read_js_array(data_path))
        self.assertIsNone(after["BD-26-001S"]["crmTitle"])
        self.assertEqual(after["BD-26-001S"]["title"], "Квартира 68 м² — Бечичи")
        self.assertEqual(after["RF-26-004G"]["crmTitle"], "Residence Lux Rafailovići")  # проект — как был


if __name__ == "__main__":
    unittest.main()
