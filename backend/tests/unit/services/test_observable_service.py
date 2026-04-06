from app.services.observable_service import extract_high_signal_entities, extract_observables


def test_extract_observables_reads_observable_value_and_deduplicates() -> None:
    timeline_items = [
        {"type": "observable", "observable_type": "IP", "observable_value": "81.2.69.160"},
        {"type": "observable", "observable_type": "IP", "observable_value": "81.2.69.160"},
    ]

    observables = extract_observables(timeline_items)

    assert len(observables) == 1
    assert observables[0].type == "IP"
    assert observables[0].value == "81.2.69.160"
    assert observables[0].count == 2


def test_extract_observables_keeps_legacy_value_fallback() -> None:
    timeline_items = [
        {"type": "observable", "observable_type": "DOMAIN", "value": "example.com"},
    ]

    observables = extract_observables(timeline_items)

    assert len(observables) == 1
    assert observables[0].type == "DOMAIN"
    assert observables[0].value == "example.com"
    assert observables[0].count == 1


def test_extract_high_signal_entities_includes_direct_observable_items() -> None:
    timeline_items = [
        {"type": "observable", "observable_type": "HASH", "observable_value": "a" * 64},
        {"type": "note", "description": "Contact admin@example.com for assistance."},
    ]

    entities = extract_high_signal_entities(timeline_items)

    assert "a" * 64 in entities
    assert "admin@example.com" not in entities