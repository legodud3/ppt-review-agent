from agent import _accumulate_tokens


def test_accumulate_tokens_adds_counts():
    tokens = {"input": 0, "output": 0, "thinking": 0}

    class FakeUsage:
        prompt_token_count = 100
        candidates_token_count = 50
        thoughts_token_count = 200

    _accumulate_tokens(FakeUsage(), tokens)
    assert tokens["input"] == 100
    assert tokens["output"] == 50
    assert tokens["thinking"] == 200


def test_accumulate_tokens_handles_none():
    tokens = {"input": 10, "output": 5, "thinking": 0}
    _accumulate_tokens(None, tokens)
    assert tokens["input"] == 10
    assert tokens["output"] == 5


def test_accumulate_tokens_handles_missing_attributes():
    tokens = {"input": 0, "output": 0, "thinking": 0}

    class MinimalUsage:
        prompt_token_count = 42

    _accumulate_tokens(MinimalUsage(), tokens)
    assert tokens["input"] == 42
    assert tokens["output"] == 0
    assert tokens["thinking"] == 0
