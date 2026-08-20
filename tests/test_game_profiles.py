from deckvoice.game_profiles import (
    DEFAULT_PROFILE,
    ensure_game_profile,
    migrate_store,
    resolve_profile,
    update_current_profile,
)

PRESETS = {"wow": {}, "generic": {}}
MODELS = ("tiny", "base", "small-q5_1", "medium-q5_0")
LANGS = ("auto", "en", "ru")


def test_migrate_flat_disables_defaults():
    store = migrate_store(
        {
            "enabled": True,
            "game": "generic",
            "buttons": ["L4", "R4"],
            "whisperModel": "tiny",
            "whisperLanguage": "ru",
        },
        PRESETS,
        MODELS,
        LANGS,
    )
    assert store["defaults"]["enabled"] is False
    assert store["defaults"]["game"] == "generic"
    assert store["defaults"]["buttons"] == ["L4", "R4"]
    assert store["defaults"]["whisperModel"] == "tiny"
    assert store["defaults"]["whisperLanguage"] == "ru"
    assert store["profiles"] == {}
    assert store["buttons"] == ["L4", "R4"]


def test_migrate_already_shaped():
    store = migrate_store(
        {
            "defaults": {"enabled": True, "game": "wow"},
            "profiles": {
                "42": {
                    "enabled": True,
                    "game": "wow",
                    "buttons": ["L1", "R1"],
                    "whisperModel": "base",
                    "whisperLanguage": "auto",
                    "name": "WoW",
                }
            },
            "buttons": ["L1", "R1"],
        },
        PRESETS,
        MODELS,
        LANGS,
    )
    assert store["defaults"]["enabled"] is False
    assert store["profiles"]["42"]["enabled"] is True
    assert store["profiles"]["42"]["name"] == "WoW"


def test_resolve_no_app_uses_defaults():
    store = migrate_store({}, PRESETS, MODELS, LANGS)
    profile = resolve_profile(store, "")
    assert profile["enabled"] is False
    assert profile["game"] == DEFAULT_PROFILE["game"]


def test_resolve_unknown_app_uses_defaults():
    store = migrate_store(
        {
            "defaults": {"enabled": False, "game": "generic", "buttons": ["A"]},
            "profiles": {},
            "buttons": ["A"],
        },
        PRESETS,
        MODELS,
        LANGS,
    )
    profile = resolve_profile(store, "999")
    assert profile["enabled"] is False
    assert profile["game"] == "generic"
    assert profile["buttons"] == ["A"]


def test_resolve_enabled_game_profile():
    store = migrate_store(
        {
            "defaults": {"enabled": False, "game": "generic"},
            "profiles": {
                "111": {
                    "enabled": True,
                    "game": "wow",
                    "buttons": ["L1", "R1"],
                    "whisperModel": "base",
                    "whisperLanguage": "auto",
                }
            },
            "buttons": ["L1", "R1"],
        },
        PRESETS,
        MODELS,
        LANGS,
    )
    profile = resolve_profile(store, "111")
    assert profile["enabled"] is True
    assert profile["game"] == "wow"
    assert profile["buttons"] == ["L1", "R1"]


def test_first_enable_copies_defaults():
    store = migrate_store(
        {
            "defaults": {
                "enabled": False,
                "game": "wow",
                "buttons": ["L2", "R2"],
                "whisperModel": "tiny",
                "whisperLanguage": "en",
            },
            "profiles": {},
            "buttons": ["L2", "R2"],
        },
        PRESETS,
        MODELS,
        LANGS,
    )
    profile = update_current_profile(store, "555", name="Test Game", enabled=True)
    assert profile["enabled"] is True
    assert profile["game"] == "wow"
    assert profile["buttons"] == ["L2", "R2"]
    assert profile["whisperModel"] == "tiny"
    assert profile["name"] == "Test Game"
    assert store["profiles"]["555"]["enabled"] is True


def test_defaults_cannot_be_enabled():
    store = migrate_store({}, PRESETS, MODELS, LANGS)
    profile = update_current_profile(store, "", enabled=True, game="generic")
    assert profile["enabled"] is False
    assert profile["game"] == "generic"


def test_ensure_game_profile_idempotent():
    store = migrate_store({}, PRESETS, MODELS, LANGS)
    first = ensure_game_profile(store, "7", "Seven")
    first["enabled"] = True
    second = ensure_game_profile(store, "7", "Seven Renamed")
    assert second["enabled"] is True
    assert second["name"] == "Seven"
