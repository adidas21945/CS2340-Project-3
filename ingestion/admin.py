from django.contrib import admin

from .models import Chunk, Document, IngestionRun, Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "publisher", "enabled", "last_ingested_at", "has_error")
    list_filter = ("source_type", "publisher", "enabled")
    search_fields = ("name", "url")

    @admin.display(boolean=True, description="Error")
    def has_error(self, obj):
        return bool(obj.last_error)


class ChunkInline(admin.TabularInline):
    model = Chunk
    extra = 0
    fields = ("index", "heading", "token_count", "text")
    readonly_fields = fields
    can_delete = False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "publisher", "source_type", "char_count", "chunk_count", "ingested_at")
    list_filter = ("publisher", "source_type")
    search_fields = ("title", "url", "cleaned_text")
    readonly_fields = ("content_hash", "cleaned_text", "char_count", "ingested_at")
    inlines = [ChunkInline]

    @admin.display(description="Chunks")
    def chunk_count(self, obj):
        return obj.chunks.count()


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = ("pk", "trigger", "status", "started_at", "sources_processed", "docs_added", "docs_updated", "docs_skipped", "chunks_added")
    list_filter = ("status", "trigger")
    readonly_fields = [f.name for f in IngestionRun._meta.fields]
