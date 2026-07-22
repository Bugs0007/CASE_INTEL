from django.conf import settings
from django.db import models


class OwnedModel(models.Model):
    """Row-level multi-tenancy: every row belongs to exactly one advocate.

    PROTECT (not CASCADE) on delete -- removing a user account must never
    silently delete their case data; the operator has to reassign or
    explicitly delete the rows first.

    Required (NOT NULL) at the DB level -- see migrations 0013-0015 for how
    existing rows were backfilled to a 'bhagath' account before this was
    enforced.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(class)ss",
    )

    class Meta:
        abstract = True
