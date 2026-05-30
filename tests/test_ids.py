from app.trace.ids import new_event_id, new_llm_call_id, new_run_id, new_trace_id


def test_id_generation_has_stable_prefixes_and_unique_values():
    assert new_trace_id().startswith("trace_")
    assert new_run_id().startswith("run_")
    assert new_event_id().startswith("evt_")
    assert new_llm_call_id().startswith("llm_")
    assert new_trace_id() != new_trace_id()
