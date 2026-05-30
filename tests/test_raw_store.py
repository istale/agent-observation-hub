from app.trace.raw_store import RawStore


def test_raw_store_writes_and_reads_json_and_jsonl(temp_data_dir):
    store = RawStore(temp_data_dir / "raw")
    ref = store.write_json("trace_abc", "llm_123_request.json", {"hello": "world"})
    chunks_ref = store.append_jsonl("trace_abc", "llm_123_chunks.jsonl", {"delta": "one"})
    store.append_jsonl("trace_abc", "llm_123_chunks.jsonl", {"delta": "two"})

    assert store.read(ref) == {"hello": "world"}
    assert store.read_jsonl(chunks_ref) == [{"delta": "one"}, {"delta": "two"}]
    assert "trace_abc" in ref
