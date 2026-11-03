"""Story #6, ingestion method 2: direct PDF upload from the website (admin only)."""
from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from .models import IngestionRun, Source
from .pipeline.ingest import run_ingestion

MAX_UPLOAD_MB = 25


class PdfUploadForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ["name", "file", "publisher", "url", "published_date"]
        labels = {"name": "Title", "url": "Original URL (optional)"}
        widgets = {"published_date": forms.DateInput(attrs={"type": "date"})}

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            raise forms.ValidationError("Choose a PDF file.")
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Only PDF files are supported.")
        if f.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"PDF must be under {MAX_UPLOAD_MB} MB.")
        return f


@staff_member_required
def upload_pdf(request):
    if request.method == "POST":
        form = PdfUploadForm(request.POST, request.FILES)
        if form.is_valid():
            source = form.save(commit=False)
            source.source_type = Source.PDF
            source.save()
            run = run_ingestion([source], trigger="upload")
            if run.status == IngestionRun.SUCCESS:
                if run.docs_skipped:
                    messages.info(request, f"'{source.name}' is already in the knowledge base.")
                else:
                    messages.success(request, f"Ingested '{source.name}': {run.chunks_added} chunks added.")
            else:
                messages.error(request, f"Could not ingest '{source.name}': {run.errors[0]['error']}")
            return redirect("ingestion:upload_pdf")
    else:
        form = PdfUploadForm()

    recent = Source.objects.filter(source_type=Source.PDF).order_by("-created_at")[:10]
    return render(request, "ingestion/upload.html", {"form": form, "recent": recent})
