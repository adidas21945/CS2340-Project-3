from unittest import mock

from django.test import TestCase
from django.urls import reverse

from ingestion.pipeline.store import InMemoryStore, VectorRecord


def make_store() -> InMemoryStore:
    store = InMemoryStore()
    meta = {"title": "Gift card scams", "url": "https://consumer.ftc.gov/articles/gift-cards", "publisher": "FTC"}
    store.add([
        VectorRecord(1, 1, "Anyone who demands payment with a gift card is a scammer.",
                     "Gift card scams. Anyone who demands payment with a gift card is a scammer.", meta),
        VectorRecord(2, 2, "Scammers pretend to be a grandchild in jail who needs bail money.",
                     "Grandkid scams. Scammers pretend to be a grandchild in jail who needs bail money.", meta),
    ])
    return store


class AskViewTests(TestCase):
    def setUp(self):
        patcher = mock.patch("chat.answer.get_store", return_value=make_store())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse("chat:ask")

    def test_page_loads_for_anyone(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Your question")

    def test_question_returns_relevant_passage_first(self):
        resp = self.client.post(self.url, {"question": "They want me to pay with a gift card"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["hits"][0].chunk_id, 1)
        self.assertContains(resp, "demands payment with a gift card")

    def test_blank_question_is_rejected(self):
        resp = self.client.post(self.url, {"question": "   "})
        self.assertIsNone(resp.context["hits"])
        self.assertTrue(resp.context["form"].errors)

    def test_empty_knowledge_base(self):
        with mock.patch("chat.answer.get_store", return_value=InMemoryStore()):
            resp = self.client.post(self.url, {"question": "Is this a scam?"})
        self.assertContains(resp, "No information found yet")
