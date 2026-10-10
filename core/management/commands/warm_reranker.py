"""Fetch the Case Bot reranker's files ahead of the first chat.

The ONNX reranker (core/services/reranker.py) downloads ~91 MB from the
Hugging Face Hub the first time it is used. Left to chance that happens
inside a web request: the first advocate to ask a question after a deploy
waits for the download, and a Hub outage at that moment disables reranking
until the next retry. Run this once per box (and after RERANKER_REVISION
changes) -- it is idempotent, and offline once the files are cached.

    python manage.py warm_reranker            # download if missing, then self-test
    python manage.py warm_reranker --no-test  # download only
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services import reranker


class Command(BaseCommand):
    help = "Download the reranker model files and check they load and score."

    def add_arguments(self, parser):
        parser.add_argument("--no-test", action="store_true", help="Skip the load-and-score check.")

    def handle(self, *args, **options):
        backend = getattr(settings, "RERANKER_BACKEND", "onnx")
        if backend != "onnx":
            self.stdout.write(f"RERANKER_BACKEND={backend}: nothing to download.")
            return

        try:
            model_path, tokenizer_path = reranker.fetch_onnx_files()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Could not fetch the reranker files: {exc}") from exc
        self.stdout.write(f"model:     {model_path}\ntokenizer: {tokenizer_path}")

        if options["no_test"]:
            return

        scorer = reranker.OnnxCrossEncoder(model_path, tokenizer_path, threads=1)
        relevant, unrelated = scorer.predict([
            ("when is the counter affidavit due",
             "The respondent shall file a counter affidavit within four weeks."),
            ("when is the counter affidavit due",
             "The lease deed stipulates monthly rent of Rs. 45,000."),
        ])
        if relevant <= unrelated:
            raise CommandError(
                f"Reranker loaded but scores look wrong (relevant={relevant:.2f}, "
                f"unrelated={unrelated:.2f})."
            )
        self.stdout.write(self.style.SUCCESS(
            f"OK: relevant passage {relevant:.2f} > unrelated {unrelated:.2f}"
        ))
