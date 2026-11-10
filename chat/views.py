"""Stories #2-#4: ask in plain language, get a grounded answer with its sources."""
from django import forms
from django.shortcuts import render

from .answer import answer_question

MAX_QUESTION_CHARS = 1000


class QuestionForm(forms.Form):
    question = forms.CharField(
        max_length=MAX_QUESTION_CHARS,
        label="Your question",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Someone called saying my grandson is in jail. Is it a scam?"}),
    )

    def clean_question(self):
        q = self.cleaned_data["question"].strip()
        if not q:
            raise forms.ValidationError("Type a question.")
        return q


def ask(request):
    question, answer = "", None
    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.cleaned_data["question"]
            answer = answer_question(question)
    else:
        form = QuestionForm()
    return render(request, "chat/ask.html", {
        "form": form,
        "question": question,
        "answer": answer,
        "hits": answer.hits if answer else None,
    })
