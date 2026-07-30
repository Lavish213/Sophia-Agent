from backend.voice.agent import (
    extract_transcript_chunks_from_messages,
    load_system_prompt,
    resolve_final_disposition,
)


def test_load_system_prompt_returns_sophia_persona():
    prompt = load_system_prompt()
    assert "Sophia" in prompt
    assert "San Joaquin House Buyers" in prompt
    assert len(prompt) > 200


def test_extract_transcript_chunks_skips_system_and_developer_messages():
    messages = [
        {"role": "system", "content": "you are sophia"},
        {"role": "developer", "content": "seed instruction"},
        {"role": "user", "content": "hi there"},
        {"role": "assistant", "content": "hey, how's it going"},
    ]
    chunks = extract_transcript_chunks_from_messages(messages)
    assert len(chunks) == 2
    assert chunks[0]["speaker"] == "seller"
    assert chunks[0]["text"] == "hi there"
    assert chunks[1]["speaker"] == "sophia"
    assert chunks[0]["sequence_order"] == 0
    assert chunks[1]["sequence_order"] == 1


def test_extract_transcript_chunks_handles_block_list_content():
    messages = [
        {"role": "assistant", "content": [{"type": "text", "text": "hey there"}, {"type": "tool_use", "id": "x"}]},
    ]
    chunks = extract_transcript_chunks_from_messages(messages)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "hey there"


def test_extract_transcript_chunks_skips_empty_text():
    messages = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "x"}]},
        {"role": "user", "content": ""},
    ]
    chunks = extract_transcript_chunks_from_messages(messages)
    assert chunks == []


def test_resolve_disposition_prefers_extracted_intel():
    result = resolve_final_disposition({"disposition": "HOT"}, "WARM", True)
    assert result == "HOT"


def test_resolve_disposition_falls_back_to_tool_when_no_intel():
    result = resolve_final_disposition(None, "COLD", True)
    assert result == "COLD"


def test_resolve_disposition_falls_back_to_tool_when_extraction_failed():
    result = resolve_final_disposition({}, "DEAD", True)
    assert result == "DEAD"


def test_resolve_disposition_defaults_to_warm_when_seller_talked_but_no_classification():
    result = resolve_final_disposition(None, None, True)
    assert result == "WARM"


def test_resolve_disposition_none_when_no_transcript_at_all():
    result = resolve_final_disposition(None, None, False)
    assert result is None
