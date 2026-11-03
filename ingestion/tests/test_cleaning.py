from django.test import SimpleTestCase

from ingestion.pipeline.cleaning import (
    clean_text,
    content_hash,
    dehyphenate,
    is_boilerplate,
    normalize_unicode,
    remove_repeated_lines,
)


class NormalizeTests(SimpleTestCase):
    def test_curly_quotes_and_dashes(self):
        self.assertEqual(normalize_unicode("“don’t pay” — ever"), "\"don't pay\" - ever")

    def test_nbsp_and_ligatures(self):
        self.assertEqual(normalize_unicode("ofﬁce hours"), "office hours")


class BoilerplateTests(SimpleTestCase):
    def test_known_lines(self):
        for line in ["Share this page", "Skip to main content", "Page 3 of 10", "12", "## Related Articles"]:
            self.assertTrue(is_boilerplate(line), line)

    def test_real_content_kept(self):
        for line in ["Never pay with gift cards.", "Report it at ReportFraud.ftc.gov", "## What to do if you paid"]:
            self.assertFalse(is_boilerplate(line), line)


class PdfCleaningTests(SimpleTestCase):
    def test_repeated_header_footer_removed(self):
        pages = [
            f"IC3 Elder Fraud Report 2024\nBody text for page {i} about scams.\nFederal Bureau of Investigation"
            for i in range(5)
        ]
        cleaned = remove_repeated_lines(pages)
        joined = "\n".join(cleaned)
        self.assertNotIn("IC3 Elder Fraud Report 2024", joined)
        self.assertNotIn("Federal Bureau of Investigation", joined)
        self.assertIn("Body text for page 3", joined)

    def test_numbered_footers_removed(self):
        pages = [f"Intro line {c}\nbody {c}\nmore body {c}\nend {c}\nPage {i} of 9" for i, c in enumerate("abcd", 1)]
        self.assertNotIn("Page", "\n".join(remove_repeated_lines(pages)))

    def test_repeated_body_text_kept(self):
        long_line = "Report fraud to the FTC at ReportFraud.ftc.gov or call 1-877-382-4357 right away, every time."
        pages = [f"H\n1\n2\n3\n{long_line}\n4\n5\n6\nF" for _ in range(4)]
        self.assertIn(long_line, "\n".join(remove_repeated_lines(pages)))

    def test_short_pdfs_untouched(self):
        pages = ["Same header\nA", "Same header\nB"]
        self.assertEqual(remove_repeated_lines(pages), pages)

    def test_dehyphenate(self):
        self.assertEqual(dehyphenate("fraud-\nulent call"), "fraudulent call")

    def test_wrapped_lines_rejoined(self):
        pages = [
            "Header\nScammers often ask you to\npay with gift cards.\n\n- Hang up\n- Call back\n7",
            "Header\nA second page of\nwrapped text.\n8",
            "Header\nThird page.\n9",
        ]
        text = clean_text(pages, is_pdf=True)
        self.assertIn("Scammers often ask you to pay with gift cards.", text)
        self.assertIn("- Hang up\n- Call back", text)
        self.assertNotIn("Header", text)
        self.assertNotRegex(text, r"(?m)^\d+$")


class HtmlCleaningTests(SimpleTestCase):
    def test_markdown_headings_survive(self):
        text = clean_text(["# Gift card scams\n\nShare this page\n\nNever   pay a stranger\twith gift cards."])
        self.assertEqual(text, "# Gift card scams\n\nNever pay a stranger with gift cards.")


class HashTests(SimpleTestCase):
    def test_whitespace_and_case_insensitive(self):
        self.assertEqual(content_hash("Hello  World\n"), content_hash("hello world"))
        self.assertNotEqual(content_hash("hello world"), content_hash("hello there"))
