"""Quick retrieval check: does the right page come back for known questions?

    python manage.py smoke_retrieval
    python manage.py smoke_retrieval --k 5 --verbose

Use this while tuning cleaning/chunking. It is the seed of story #9.
Edit ingestion/eval/smoke_questions.json to add questions.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ingestion.pipeline.store import get_store

QUESTIONS_FILE = Path(__file__).resolve().parents[2] / "eval" / "smoke_questions.json"


class Command(BaseCommand):
    help = "Check that known questions retrieve the expected source in the top k."

    def add_arguments(self, parser):
        parser.add_argument("--k", type=int, default=3)
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **opts):
        store = get_store()
        questions = json.loads(QUESTIONS_FILE.read_text())
        hits = 0
        for q in questions:
            results = store.search(q["question"], k=opts["k"])
            expected = [e.lower() for e in q["expected_url_contains"]]
            ok = any(any(e in r.url.lower() for e in expected) for r in results)
            hits += ok
            mark = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
            self.stdout.write(f"{mark} {q['question']}")
            if opts["verbose"] or not ok:
                for r in results:
                    self.stdout.write(f"     {r.score:.3f}  {r.title} > {r.heading or '-'}  ({r.url})")
        self.stdout.write(f"\nTop-{opts['k']} hit rate: {hits}/{len(questions)}")
