import json

from db_migrations.v0_6_0 import timeline_search
from app.services.observable_correlation import CORRELATION_FIELD_MAPPINGS, correlation_field_records
from app.services.search_service import FIELD_MAPPINGS


def test_correlation_fields_use_the_same_indexed_vocabulary_as_queue_matching() -> None:
    required = {"observable_value", "value"}
    for mappings in (FIELD_MAPPINGS, CORRELATION_FIELD_MAPPINGS):
        for fields in mappings.values():
            required.update(field for _, field in fields)
    assert required <= set(timeline_search.INDEXED_FIELDS)


def test_correlation_field_records_bind_type_and_field_as_data() -> None:
    assert json.loads(correlation_field_records("URL")) == [
        {"item_type": "attachment", "field_name": "url"},
        {"item_type": "ttp", "field_name": "url"},
        {"item_type": "link", "field_name": "url"},
        {"item_type": "forensic_artifact", "field_name": "url"},
    ]
    assert json.loads(correlation_field_records("UNKNOWN")) == []
