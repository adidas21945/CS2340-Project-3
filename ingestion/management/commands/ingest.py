"""Run the ingestion pipeline.

    python manage.py ingest                 # every enabled source
    python manage.py ingest --source 3 7    # specific source ids
    python manage.py ingest --clear         # wipe the knowledge base, then reload all
"""
from django.core.management.base import BaseCommand

from ingestion.models import Source
from ingestion.pipeline.ingest import clear_knowledge_base, run_ingestion


class Command(BaseCommand):
    help = "Scrape/load sources, clean, chunk and store them in the vector store."

    def add_arguments(self, parser):
        parser.add_argument("--source", nargs="+", type=int, help="Only these Source ids")
        parser.add_argument("--clear", action="store_true", help="Wipe documents and vectors first")

    def handle(self, *args, **opts):
        if opts["clear"]:
            clear_knowledge_base()
            self.stdout.write("Knowledge base cleared.")

        sources = Source.objects.filter(enabled=True)
        if opts["source"]:
            sources = sources.filter(pk__in=opts["source"])
        if not sources.exists():
            self.stdout.write(self.style.WARNING("No enabled sources. Run `python manage.py seed_sources` first."))
            return

        run = run_ingestion(sources, trigger="reload" if opts["clear"] else "command")
        self.stdout.write(
            f"Run {run.pk}: {run.status} in {run.duration_seconds:.1f}s | "
            f"sources {run.sources_processed} | added {run.docs_added} | updated {run.docs_updated} | "
            f"unchanged {run.docs_skipped} | chunks {run.chunks_added}"
        )
        for err in run.errors:
            self.stdout.write(self.style.ERROR(f"  {err['source']}: {err['error']}"))
