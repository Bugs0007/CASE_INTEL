from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    # Matches what the database actually has: migration 0004 altered every
    # pk to BigAutoField (bigint). Without this line Django's model state
    # defaults to AutoField and makemigrations perpetually wants to
    # downgrade every pk back to int (the 20 W042 warnings + phantom
    # AlterField operations seen before this was set).
    default_auto_field = "django.db.models.BigAutoField"
