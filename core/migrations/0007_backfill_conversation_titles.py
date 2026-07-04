from django.db import migrations


def _normalize_whitespace(value):
    return " ".join((value or "").split())


def _truncate_on_word_boundary(value, max_length):
    text = _normalize_whitespace(value)
    if not text:
        return ""
    if len(text) <= max_length:
        return text

    candidate = text[: max_length + 1]
    head = candidate[:max_length].rstrip(" ,;:-")
    if " " in head:
        trimmed = head.rsplit(" ", 1)[0].rstrip(" ,;:-")
        if trimmed and len(trimmed) >= max(12, max_length // 2):
            return trimmed
    return head


def _generate_title(first_user_message):
    return _truncate_on_word_boundary(first_user_message, 50) or "New Conversation"


def backfill_conversation_titles(apps, schema_editor):
    Conversation = apps.get_model("core", "Conversation")
    Message = apps.get_model("core", "Message")

    for conversation in Conversation.objects.filter(title__isnull=True) | Conversation.objects.filter(title=""):
        first_user_message = (
            Message.objects.filter(conversation_id=conversation.id, role="user")
            .order_by("created_at")
            .values_list("content", flat=True)
            .first()
        )
        conversation.title = _generate_title(first_user_message)
        conversation.save(update_fields=["title"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_merge_20260702_1549"),
    ]

    operations = [
        migrations.RunPython(backfill_conversation_titles, migrations.RunPython.noop),
    ]
