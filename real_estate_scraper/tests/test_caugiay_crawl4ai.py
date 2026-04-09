import importlib.util
import unittest
from pathlib import Path


def _load_caugiay_module():
    module_path = Path(__file__).resolve().parents[1] / "spiders" / "test.py"
    spec = importlib.util.spec_from_file_location("caugiay_crawl4ai", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_caugiay_module()


class TestCauGiayCrawl4AI(unittest.TestCase):
    def test_extract_listing_links_filters_noise(self):
        html = """
        <html><body>
            <a href="/ban-nha-rieng-duong-abc-phuong-xyz/test-pr123">ok1</a>
            <a href="/ban-can-ho-chung-cu-duong-abc/test-pr456">ok2</a>
            <a href="/ban-can-ho-chung-cu-duong-abc/test-pr456">duplicate</a>
            <a href="/assets/site.css-pr789">css-should-be-filtered</a>
            <a href="javascript:void(0)">ignore-js</a>
            <a href="https://example.com/ban-nha-rieng-foo-pr999">other-domain</a>
        </body></html>
        """

        links = mod._extract_listing_links(html, max_items=10)
        self.assertEqual(len(links), 2)
        self.assertTrue(links[0].startswith("https://batdongsan.com.vn/"))
        self.assertIn("-pr123", links[0])
        self.assertIn("-pr456", links[1])

    def test_json_ld_candidates_supports_dict_and_list(self):
        html = """
        <script type="application/ld+json">{"@type":"BreadcrumbList"}</script>
        <script type="application/ld+json">[{"@type":"Product"},{"@type":"Article"}]</script>
        """

        items = mod._json_ld_candidates(html)
        types = sorted([x.get("@type") for x in items])
        self.assertEqual(types, ["Article", "BreadcrumbList", "Product"])

    def test_best_jsonld_candidate_prefers_listing_like_object(self):
        candidates = [
            {"@type": "BreadcrumbList", "name": "crumb"},
            {
                "@type": "Product",
                "name": "Listing A",
                "offers": {"price": "12.5", "priceCurrency": "VND"},
                "address": {"streetAddress": "Cau Giay"},
            },
        ]

        best = mod._best_jsonld_candidate(candidates)
        self.assertEqual(best.get("name"), "Listing A")

    def test_parse_detail_from_jsonld(self):
        url = "https://batdongsan.com.vn/ban-nha-rieng-foo-pr123456"
        html = """
        <html><head>
          <title>Fallback Title</title>
          <script type="application/ld+json">
          {
            "@type": "Product",
            "name": "Nice House Cau Giay",
            "description": "Great location",
            "category": "House",
            "address": {"streetAddress": "123 Xuan Thuy"},
            "offers": {"price": "26.9", "priceCurrency": "VND"},
            "floorSize": {"value": "50", "unitCode": "m2"}
          }
          </script>
        </head><body></body></html>
        """

        row = mod._parse_detail(html, url)
        self.assertEqual(row["source"], "batdongsan.com.vn")
        self.assertEqual(row["title"], "Nice House Cau Giay")
        self.assertEqual(row["description"], "Great location")
        self.assertEqual(row["address"], "123 Xuan Thuy")
        self.assertIn("26.9", row["price"])
        self.assertEqual(row["property_type"], "House")
        self.assertIn("50", row["property_size"])
        self.assertEqual(row["listing_id"], "123456")
        self.assertEqual(row["crawl_status"], "ok")

    def test_parse_detail_fallback_url_inference(self):
        url = "https://batdongsan.com.vn/ban-can-ho-chung-cu-foo-pr998877"
        html = """
        <html><head><title>Can ho trung tam</title></head>
        <body>
          Gia: 7,5 ty
          Dien tich: 70 m2
          3 phong ngu, 2 wc
        </body></html>
        """

        row = mod._parse_detail(html, url)
        self.assertEqual(row["property_type"], "Apartment")
        self.assertIn("7,5", row["price_raw"])
        self.assertIn("70", row["property_size_raw"])
        self.assertEqual(row["bedrooms"], "3")
        self.assertEqual(row["bathrooms"], "2")


if __name__ == "__main__":
    unittest.main()
