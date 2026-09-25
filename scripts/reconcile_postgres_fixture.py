"""Map the legacy Garima organization ID onto the starter row in PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.apps import apps
from django.conf import settings
from accounts.models import Company


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Fixture exported from the legacy database")
    parser.add_argument("destination", type=Path, help="New reconciled fixture path")
    args = parser.parse_args()

    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise SystemExit("Refusing to run: Django is not configured for PostgreSQL.")
    if not args.source.is_file():
        raise SystemExit(f"Source fixture not found: {args.source}")
    if args.destination.exists():
        raise SystemExit(f"Destination already exists; refusing to overwrite: {args.destination}")

    records = json.loads(args.source.read_text(encoding="utf-8"))
    company_records = [
        record for record in records
        if record.get("model", "").lower() == "accounts.company"
        and record.get("fields", {}).get("slug") == "garima-engineering-consultancy"
    ]
    if len(company_records) != 1:
        raise SystemExit(f"Expected one Garima company record in fixture; found {len(company_records)}.")

    company_record = company_records[0]
    source_company_id = company_record["pk"]
    target_company = Company.objects.get(slug="garima-engineering-consultancy")
    target_company_id = target_company.pk
    remapped_foreign_keys = 0

    for record in records:
        app_label, model_name = record["model"].split(".", 1)
        model = apps.get_model(app_label, model_name)
        fields = record.get("fields", {})

        if record is company_record:
            record["pk"] = target_company_id

        for field in model._meta.concrete_fields:
            if not field.is_relation or field.remote_field.model is not Company:
                continue
            value = fields.get(field.name)
            if value == source_company_id:
                fields[field.name] = target_company_id
                remapped_foreign_keys += 1

    for record in records:
        app_label, model_name = record["model"].split(".", 1)
        model = apps.get_model(app_label, model_name)
        if model is Company and record is company_record:
            continue
        if model._base_manager.using("default").filter(pk=record.get("pk")).exists():
            raise SystemExit(
                f"Target PostgreSQL already has {record['model']} pk={record.get('pk')}; "
                "fixture was not written. Inspect before importing."
            )

    args.destination.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Mapped Garima company ID {source_company_id} to existing PostgreSQL ID {target_company_id}.")
    print(f"Organization foreign-key references remapped: {remapped_foreign_keys}.")
    print(f"Reconciled fixture written to: {args.destination}")


if __name__ == "__main__":
    main()
