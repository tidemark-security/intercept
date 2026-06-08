import json

from app.services.enrichment.providers.cross_case_observable import cross_case_observable_provider


def test_build_match_sql_binds_mapping_values() -> None:
    prefilter_sql, match_sql, params = cross_case_observable_provider._build_match_sql("URL")
    combined_sql = f"{prefilter_sql}\n{match_sql}"

    assert ":candidate_object_path_0" in prefilter_sql
    assert ":field_mappings" in match_sql
    assert "attachment" not in combined_sql
    assert "forensic_artifact" not in combined_sql
    assert "url" not in combined_sql
    candidate_paths = [value for key, value in params.items() if key.startswith("candidate_")]
    assert '$.* ? (@.type == "attachment")' in candidate_paths
    assert '$[*] ? (@.type == "forensic_artifact")' in candidate_paths
    assert json.loads(params["field_mappings"]) == [
        {"item_type": "attachment", "field_name": "url"},
        {"item_type": "ttp", "field_name": "url"},
        {"item_type": "link", "field_name": "url"},
        {"item_type": "forensic_artifact", "field_name": "url"},
    ]


def test_build_match_sql_unknown_type_matches_only_observable_items() -> None:
    prefilter_sql, match_sql, params = cross_case_observable_provider._build_match_sql("UNKNOWN")

    assert ":field_mappings" in match_sql
    assert prefilter_sql == (
        "timeline_items @? CAST(:candidate_object_path_0 AS jsonpath) OR "
        "timeline_items @? CAST(:candidate_array_path_0 AS jsonpath)"
    )
    assert params["candidate_object_path_0"] == '$.* ? (@.type == "observable")'
    assert params["candidate_array_path_0"] == '$[*] ? (@.type == "observable")'
    assert json.loads(params["field_mappings"]) == []
