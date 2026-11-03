from django.test import SimpleTestCase

from ingestion.pipeline.chunking import chunk_text, estimate_tokens, split_sections, text_for_embedding


def words(n, word="scam"):
    return " ".join([word] * n) + "."


class SectionTests(SimpleTestCase):
    def test_heading_path(self):
        text = "# Gift card scams\nIntro.\n## What to do\nCall the company.\n# Romance scams\nBe careful."
        sections = split_sections(text)
        self.assertEqual(
            [h for h, _ in sections],
            ["Gift card scams", "Gift card scams > What to do", "Romance scams"],
        )

    def test_no_headings(self):
        self.assertEqual(split_sections("Just text."), [("", "Just text.")])


class ChunkTests(SimpleTestCase):
    def test_chunks_respect_max_size(self):
        text = "\n\n".join(words(100) for _ in range(20))  # ~2,700 tokens
        chunks = chunk_text(text, max_tokens=500, overlap_tokens=50)
        self.assertGreater(len(chunks), 4)
        for c in chunks:
            self.assertLessEqual(c.token_count, 500 + 70)  # overlap may add a little

    def test_overlap_carried(self):
        paras = [f"Paragraph {i} " + words(150, f"w{i}") for i in range(4)]
        chunks = chunk_text("\n\n".join(paras), max_tokens=250, overlap_tokens=50)
        # the tail of chunk 0 should reappear at the start of chunk 1
        tail = chunks[0].text.split()[-5:]
        self.assertTrue(all(w in chunks[1].text for w in tail))

    def test_sections_not_mixed(self):
        text = f"# Gift cards\n{words(80, 'gift')}\n# Romance\n{words(80, 'love')}"
        chunks = chunk_text(text)
        self.assertEqual([c.heading for c in chunks], ["Gift cards", "Romance"])
        self.assertNotIn("love", chunks[0].text)

    def test_tiny_fragments_dropped_and_reindexed(self):
        text = f"# A\nToo short.\n# B\n{words(80)}\n# C\n{words(80)}"
        chunks = chunk_text(text, min_tokens=40)
        self.assertEqual([c.heading for c in chunks], ["B", "C"])
        self.assertEqual([c.index for c in chunks], [0, 1])

    def test_long_paragraph_split_by_sentence(self):
        para = " ".join(f"Sentence {i} " + words(30) for i in range(40))
        chunks = chunk_text(para, max_tokens=300)
        self.assertGreater(len(chunks), 1)

    def test_embedding_text_has_context(self):
        chunk = chunk_text(f"# What to do\n{words(60)}")[0]
        self.assertTrue(text_for_embedding(chunk, "Gift card scams").startswith("Gift card scams > What to do"))

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens("one two three"), 4)
