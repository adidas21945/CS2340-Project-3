import tempfile
from unittest import mock

import pymupdf
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ingestion.models import Chunk, Document, IngestionRun, Source
from ingestion.pipeline import ingest
from ingestion.pipeline.loaders import LoaderError, html_to_rawdoc, load_pdf
from ingestion.pipeline.store import InMemoryStore
from ingestion.pipeline.types import RawDoc

GIFT_CARD_HTML = """
<html><head><title>Avoiding and Reporting Gift Card Scams | Consumer Advice</title></head>
<body>
<nav><a href="/">Home</a> <a href="/scams">Scams</a> Skip to main content</nav>
<main><article>
<h1>Avoiding and Reporting Gift Card Scams</h1>
<p>Gift cards are for gifts, not payments. Anyone who demands to be paid with a gift card is
always a scammer. Scammers say you need to pay a bill, fix a computer problem, or help a family
member in trouble, and they tell you to buy gift cards from a store like Walmart or Target.</p>
<h2>What to do if you paid a scammer with a gift card</h2>
<p>Contact the company that issued the gift card right away. Tell them the gift card was used in a
scam and ask if they can refund your money. Keep the gift card itself and the store receipt.
Then report it to the FTC at ReportFraud.ftc.gov. The sooner you act, the better the chance the
company can freeze the funds before the scammer spends them.</p>
</article></main>
<footer>Share this page. Federal Trade Commission. Privacy policy.</footer>
</body></html>
"""


def make_pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


PDF_BODIES = [
    "People over 60 reported losing billions to fraud last year, more than any other age group.",
    "Tech support scams and government impersonation scams were the most common complaints.",
    "Scammers asked victims to pay with wire transfers, cryptocurrency and gift cards.",
    "Victims were often told to keep the payment secret from family and from bank staff.",
]
PDF_PAGES = [
    "Elder Fraud Report\n\n" + "\n".join([body] * 6) + f"\n\nPage {i + 1}"
    for i, body in enumerate(PDF_BODIES)
]


class LoaderTests(TestCase):
    def test_html_main_content_only(self):
        raw = html_to_rawdoc(GIFT_CARD_HTML, url="https://consumer.ftc.gov/articles/gift-cards")
        text = raw.pages[0]
        self.assertIn("Gift cards are for gifts", text)
        self.assertIn("What to do if you paid a scammer", text)
        self.assertNotIn("Privacy policy", text)
        self.assertEqual(raw.publisher, "FTC")
        self.assertTrue(raw.has_markdown_headings)

    def test_pdf_pages(self):
        raw = load_pdf(make_pdf_bytes(PDF_PAGES), title="IC3 report", publisher="FBI")
        self.assertEqual(len(raw.pages), 4)
        self.assertEqual(raw.source_type, "pdf")


class IngestTests(TestCase):
    def setUp(self):
        self.store = InMemoryStore()

    def _raw(self, **kw):
        return html_to_rawdoc(GIFT_CARD_HTML, url="https://consumer.ftc.gov/articles/gift-cards", **kw)

    def test_ingest_stores_chunks_with_metadata(self):
        status, n = ingest.ingest_rawdoc(self._raw(), store=self.store)
        self.assertEqual(status, ingest.ADDED)
        self.assertEqual(Chunk.objects.count(), n)
        self.assertEqual(self.store.count(), n)

        hit = self.store.search("I paid with a gift card, what now?", k=1)[0]
        self.assertEqual(hit.url, "https://consumer.ftc.gov/articles/gift-cards")
        self.assertEqual(hit.publisher, "FTC")
        self.assertTrue(Chunk.objects.filter(pk=hit.chunk_id).exists())

    def test_same_content_is_skipped(self):
        ingest.ingest_rawdoc(self._raw(), store=self.store)
        status, n = ingest.ingest_rawdoc(self._raw(), store=self.store)
        self.assertEqual((status, n), (ingest.SKIPPED, 0))
        self.assertEqual(Document.objects.count(), 1)

    def test_changed_page_replaces_old_version(self):
        ingest.ingest_rawdoc(self._raw(), store=self.store)
        old_ids = set(Chunk.objects.values_list("pk", flat=True))
        changed = self._raw()
        changed.pages = [changed.pages[0] + "\n\nNew: scammers now also ask for Apple gift cards over text message."]
        status, _ = ingest.ingest_rawdoc(changed, store=self.store)
        self.assertEqual(status, ingest.UPDATED)
        self.assertEqual(Document.objects.count(), 1)
        self.assertFalse(Chunk.objects.filter(pk__in=old_ids).exists())
        self.assertTrue(all(h.chunk_id not in old_ids for h in self.store.search("gift card", k=20)))

    def test_too_short_document_rejected(self):
        raw = RawDoc(pages=["Page not found"], title="404", source_type="scrape", url="https://x.gov/a")
        with self.assertRaises(ValueError):
            ingest.ingest_rawdoc(raw, store=self.store)

    def test_run_logs_errors_and_continues(self):
        good = Source.objects.create(name="Gift cards", source_type=Source.SCRAPE, url="https://consumer.ftc.gov/a", publisher="FTC")
        bad = Source.objects.create(name="Broken", source_type=Source.SCRAPE, url="https://consumer.ftc.gov/b", publisher="FTC")

        def fake_fetch(url):
            if url.endswith("/b"):
                raise LoaderError("GET returned 404")
            return GIFT_CARD_HTML

        with mock.patch("ingestion.pipeline.loaders.fetch_html", side_effect=fake_fetch):
            run = ingest.run_ingestion([good, bad], store=self.store)

        self.assertEqual(run.status, IngestionRun.PARTIAL)
        self.assertEqual(run.docs_added, 1)
        self.assertEqual(len(run.errors), 1)
        bad.refresh_from_db()
        self.assertIn("404", bad.last_error)

    def test_clear_knowledge_base(self):
        ingest.ingest_rawdoc(self._raw(), store=self.store)
        ingest.clear_knowledge_base(store=self.store)
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(self.store.count(), 0)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class UploadViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(user)
        self.store = InMemoryStore()
        patcher = mock.patch("ingestion.pipeline.ingest.get_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_requires_staff(self):
        self.client.logout()
        resp = self.client.get(reverse("ingestion:upload_pdf"))
        self.assertEqual(resp.status_code, 302)

    def test_upload_ingests_pdf(self):
        pdf = SimpleUploadedFile("ic3.pdf", make_pdf_bytes(PDF_PAGES), content_type="application/pdf")
        resp = self.client.post(
            reverse("ingestion:upload_pdf"),
            {"name": "IC3 Elder Fraud Report", "publisher": "FBI", "file": pdf},
            follow=True,
        )
        self.assertContains(resp, "chunks added")
        doc = Document.objects.get()
        self.assertEqual(doc.source_type, "pdf")
        self.assertNotIn("Page 2", doc.cleaned_text)  # page-number footer stripped
        self.assertNotIn("Elder Fraud Report", doc.cleaned_text)  # running header stripped
        self.assertIn("gift cards", doc.cleaned_text)
        self.assertGreater(self.store.count(), 0)

    def test_rejects_non_pdf(self):
        txt = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        resp = self.client.post(reverse("ingestion:upload_pdf"), {"name": "x", "file": txt})
        self.assertContains(resp, "Only PDF files")
        self.assertEqual(Source.objects.count(), 0)
