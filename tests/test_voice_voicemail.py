from backend.voice import voicemail


def test_human_answer_is_not_a_machine():
    assert voicemail.is_human("human") is True
    assert voicemail.is_machine("human") is False


def test_missing_answered_by_is_treated_as_human():
    assert voicemail.is_human("") is True
    assert voicemail.is_human(None) is True
    assert voicemail.is_machine(None) is False


def test_machine_start_is_machine_but_not_ready_for_message():
    assert voicemail.is_machine("machine_start") is True
    assert voicemail.should_leave_voicemail("machine_start") is False


def test_machine_end_variants_are_ready_for_message():
    for value in ("machine_end_beep", "machine_end_silence", "machine_end_other"):
        assert voicemail.should_leave_voicemail(value) is True


def test_fax_and_unknown_are_unusable():
    assert voicemail.is_unusable("fax") is True
    assert voicemail.is_unusable("unknown") is True
    assert voicemail.is_unusable("human") is False


def test_answered_by_is_case_insensitive():
    assert voicemail.is_machine("MACHINE_END_BEEP") is True
    assert voicemail.should_leave_voicemail("Machine_End_Beep") is True


def test_voicemail_script_uses_owner_first_name():
    lead = {"properties": {"owner_name": "Maria Gonzalez"}}
    script = voicemail.build_voicemail_script(lead, 1)
    assert "Hi Maria," in script


def test_voicemail_script_without_name_is_still_natural():
    script = voicemail.build_voicemail_script(None, 1)
    assert "Hi there," in script


def test_voicemail_script_varies_by_attempt():
    first = voicemail.build_voicemail_script(None, 1)
    second = voicemail.build_voicemail_script(None, 2)
    third = voicemail.build_voicemail_script(None, 3)
    assert first != second != third
    assert "following up" in second
    assert "won't keep bugging you" in third


def test_voicemail_laml_escapes_and_hangs_up():
    laml = voicemail.build_voicemail_laml("Tom & Jerry <test>")
    assert "&amp;" in laml
    assert "&lt;test&gt;" in laml
    assert "<Hangup/>" in laml
    assert laml.startswith("<?xml")


def test_hangup_laml_is_valid():
    assert voicemail.build_hangup_laml().endswith("<Response><Hangup/></Response>")


def test_spoken_phone_is_readable_digit_groups():
    assert voicemail._spoken_phone("+12095551212") == "2 0 9, 5 5 5, 1 2 1 2"


def test_spoken_phone_passes_through_unparseable():
    assert voicemail._spoken_phone("ext 5") == "ext 5"
