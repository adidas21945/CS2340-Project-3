"""Load the starting list of FTC / FBI pages into the Source table.

    python manage.py seed_sources

Safe to re-run: existing URLs are left alone. Any URL that 404s shows up in the
ingest run's errors; fix or disable it in /admin/ingestion/source/.
"""
from django.core.management.base import BaseCommand

from ingestion.models import Source

SEED_PAGES = [
    # (name, url, publisher)
    ("How to avoid a scam", "https://consumer.ftc.gov/articles/how-avoid-scam", "FTC"),
    ("What to do if you were scammed", "https://consumer.ftc.gov/articles/what-do-if-you-were-scammed", "FTC"),
    ("How to recognize and avoid phishing scams", "https://consumer.ftc.gov/articles/how-recognize-and-avoid-phishing-scams", "FTC"),
    ("Tech support scams", "https://consumer.ftc.gov/articles/how-spot-avoid-and-report-tech-support-scams", "FTC"),
    ("Romance scams", "https://consumer.ftc.gov/articles/what-know-about-romance-scams", "FTC"),
    ("Gift card scams", "https://consumer.ftc.gov/articles/avoiding-and-reporting-gift-card-scams", "FTC"),
    ("Cryptocurrency scams", "https://consumer.ftc.gov/articles/what-know-about-cryptocurrency-and-scams", "FTC"),
    ("Fake prize, sweepstakes and lottery scams", "https://consumer.ftc.gov/articles/fake-prize-sweepstakes-and-lottery-scams", "FTC"),
    ("Impersonator scams", "https://consumer.ftc.gov/features/pass-it-on/impersonator-scams", "FTC"),
    ("Grandkid and family emergency scams", "https://consumer.ftc.gov/features/pass-it-on/imposter-scams/grandkid-scams", "FTC"),
    ("Investment scams", "https://consumer.ftc.gov/articles/investment-scams", "FTC"),
    ("Phone scams", "https://consumer.ftc.gov/articles/phone-scams", "FTC"),
    ("Text message scams", "https://consumer.ftc.gov/articles/how-recognize-and-report-spam-text-messages", "FTC"),
    ("Pass It On: scams against older adults", "https://consumer.ftc.gov/features/pass-it-on", "FTC"),
    (
        "Business and government impersonators go after older adults' life savings",
        "https://consumer.ftc.gov/consumer-alerts/2025/08/business-and-government-impersonators-go-after-older-adults-life-savings",
        "FTC",
    ),
    ("IRS imposter scams", "https://consumer.ftc.gov/features/pass-it-on/imposter-scams/irs-imposter-scams", "FTC"),
    ("Unwanted calls and text messages", "https://consumer.ftc.gov/features/pass-it-on/unwanted-calls-and-text-messages", "FTC"),
    ("Business impersonator scams", "https://consumer.ftc.gov/features/pass-it-on/business-impersonator-scams", "FTC"),
    ("Identity theft", "https://consumer.ftc.gov/features/pass-it-on/identity-theft", "FTC"),
    # fbi.gov returns 403 to scrapers. Add FBI/IC3 guidance as PDFs at /ingestion/upload/
    # (e.g. the IC3 Elder Fraud Report).
]


class Command(BaseCommand):
    help = "Add the starter FTC/FBI web pages as scrape sources."

    def handle(self, *args, **opts):
        created = 0
        for name, url, publisher in SEED_PAGES:
            _, was_created = Source.objects.get_or_create(
                url=url,
                defaults={"name": name, "source_type": Source.SCRAPE, "publisher": publisher},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"{created} new sources ({Source.objects.count()} total)"))
