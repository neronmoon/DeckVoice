DEFAULT_PROFILE = {
    "enabled": False,
    "game": "wow",
    "buttons": ["L1", "R1"],
    "whisperModel": "base",
    "whisperLanguage": "auto",
}

PROFILE_KEYS = ("enabled", "game", "buttons", "whisperModel", "whisperLanguage")


def normalize_profile(raw, presets, models, languages):
    profile = dict(DEFAULT_PROFILE)
    if isinstance(raw, dict):
        for key in PROFILE_KEYS:
            if key in raw:
                profile[key] = raw[key]
        if raw.get("name"):
            profile["name"] = raw["name"]
    profile["enabled"] = bool(profile.get("enabled"))
    if profile.get("game") not in presets:
        profile["game"] = "wow"
    if profile.get("whisperModel") not in models:
        profile["whisperModel"] = "base"
    if profile.get("whisperLanguage") not in languages:
        profile["whisperLanguage"] = "auto"
    if not isinstance(profile.get("buttons"), list) or not profile["buttons"]:
        profile["buttons"] = list(DEFAULT_PROFILE["buttons"])
    return profile


def empty_store():
    return {
        "defaults": dict(DEFAULT_PROFILE),
        "profiles": {},
        "buttons": list(DEFAULT_PROFILE["buttons"]),
    }


def migrate_store(raw, presets, models, languages):
    if not isinstance(raw, dict):
        return empty_store()
    if "defaults" in raw or "profiles" in raw:
        store = empty_store()
        store["defaults"] = normalize_profile(raw.get("defaults"), presets, models, languages)
        store["defaults"]["enabled"] = False
        profiles = raw.get("profiles") or {}
        if isinstance(profiles, dict):
            for app_id, profile in profiles.items():
                key = str(app_id)
                if not key:
                    continue
                store["profiles"][key] = normalize_profile(profile, presets, models, languages)
        active = raw.get("buttons")
        if isinstance(active, list) and active:
            store["buttons"] = active
        else:
            store["buttons"] = list(store["defaults"]["buttons"])
        return store

    store = empty_store()
    migrated = normalize_profile(raw, presets, models, languages)
    migrated["enabled"] = False
    store["defaults"] = migrated
    store["buttons"] = list(migrated["buttons"])
    return store


def resolve_profile(store, app_id):
    if app_id:
        profile = store.get("profiles", {}).get(str(app_id))
        if profile is not None:
            return dict(profile)
    return dict(store.get("defaults") or DEFAULT_PROFILE)


def ensure_game_profile(store, app_id, name=None):
    key = str(app_id)
    profiles = store.setdefault("profiles", {})
    if key not in profiles:
        profile = dict(store.get("defaults") or DEFAULT_PROFILE)
        profile["enabled"] = False
        if name:
            profile["name"] = name
        profiles[key] = profile
    elif name and not profiles[key].get("name"):
        profiles[key]["name"] = name
    return profiles[key]


def update_current_profile(store, app_id, **kwargs):
    if app_id:
        profile = ensure_game_profile(store, app_id, kwargs.pop("name", None))
    else:
        profile = store.setdefault("defaults", dict(DEFAULT_PROFILE))
        kwargs.pop("name", None)
        if "enabled" in kwargs:
            kwargs["enabled"] = False
    for key, value in kwargs.items():
        if key in PROFILE_KEYS or key == "name":
            profile[key] = value
    if "buttons" in kwargs and isinstance(kwargs["buttons"], list) and kwargs["buttons"]:
        store["buttons"] = list(kwargs["buttons"])
    return profile
