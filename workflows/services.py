from __future__ import annotations

from django.db import transaction

from workflows.models import NumberingScheme


def allocate_project_number(service_type) -> str:
    with transaction.atomic():
        scheme = NumberingScheme.objects.select_for_update().get(service_type=service_type, is_active=True)
        sequence = scheme.next_sequence
        scheme.next_sequence += 1
        scheme.save(update_fields=["next_sequence", "updated_at"])
        return scheme.render_number(sequence)

