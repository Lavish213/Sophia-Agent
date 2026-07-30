import os

from backend.lib.config import Settings


def _env_example_keys() -> set[str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_root, ".env.example")
    keys = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            keys.add(line.split("=", 1)[0])
    return keys


def _settings_field_env_names() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def test_every_settings_field_is_in_env_example():
    missing = _settings_field_env_names() - _env_example_keys()
    assert not missing, f"Fields missing from .env.example: {missing}"


def test_every_env_example_key_is_a_settings_field():
    extra = _env_example_keys() - _settings_field_env_names()
    assert not extra, f".env.example has keys not in Settings: {extra}"
