from django.db import models


class Source(models.Model):
    """One entry in the knowledge base definition (story #5 edits this table).

    A scrape source has a url. A PDF source has a file (and optionally the url
    where the PDF was published, so answers can link to it).
    """

    SCRAPE = "scrape"
    PDF = "pdf"
    TYPE_CHOICES = [(SCRAPE, "Web page (scraped)"), (PDF, "PDF upload")]

    name = models.CharField(max_length=300)
    source_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    url = models.URLField(max_length=1000, blank=True)
    file = models.FileField(upload_to="sources/", blank=True)
    publisher = models.CharField(max_length=100, blank=True, help_text="e.g. FTC, FBI")
    published_date = models.DateField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_ingested_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["publisher", "name"]

    def __str__(self):
        return f"[{self.get_source_type_display()}] {self.name}"


class Document(models.Model):
    """A cleaned document that made it into the knowledge base."""

    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000, blank=True)
    publisher = models.CharField(max_length=100, blank=True)
    published_date = models.DateField(null=True, blank=True)
    source_type = models.CharField(max_length=10, choices=Source.TYPE_CHOICES)
    content_hash = models.CharField(max_length=64, unique=True)
    cleaned_text = models.TextField()
    char_count = models.PositiveIntegerField(default=0)
    ingested_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Chunk(models.Model):
    """One retrievable piece of a Document. Its pk is the vector store id."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    heading = models.CharField(max_length=500, blank=True)
    text = models.TextField()
    token_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["document", "index"]
        unique_together = [("document", "index")]

    def __str__(self):
        return f"{self.document.title} #{self.index}"


class IngestionRun(models.Model):
    """Log of each ingestion. Feeds the admin monitoring/log stories (#10, #12)."""

    RUNNING, SUCCESS, PARTIAL, FAILED = "running", "success", "partial", "failed"
    STATUS_CHOICES = [(s, s) for s in (RUNNING, SUCCESS, PARTIAL, FAILED)]

    trigger = models.CharField(max_length=50, default="manual", help_text="command, upload, reload")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=RUNNING)
    sources_processed = models.PositiveIntegerField(default=0)
    docs_added = models.PositiveIntegerField(default=0)
    docs_updated = models.PositiveIntegerField(default=0)
    docs_skipped = models.PositiveIntegerField(default=0)
    chunks_added = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]

    @property
    def duration_seconds(self):
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def __str__(self):
        return f"Run {self.pk} ({self.status}) {self.started_at:%Y-%m-%d %H:%M}"
