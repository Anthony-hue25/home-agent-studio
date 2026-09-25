"""Closed, deterministic preference catalog and bounded interpretation contract.

Gate D keeps the model on the safe side of the boundary:
- code creates the only valid preference/value/scope/subject references;
- a model may map natural language only onto those opaque references;
- ambiguity is surfaced as NEEDS_CLARIFICATION;
- arbitrary numeric setpoints or invented references fail closed.
"""
from dataclasses import dataclass
from .audit import digest
from .stay import PropertyProfile, PropertyTwin, StayProfile, ScopedPreference

INTERPRETATION_STATES = ("RESOLVED", "NEEDS_CLARIFICATION", "UNSUPPORTED")


def _bounded_text(value, label, maximum=2000):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


@dataclass(frozen=True)
class PreferenceChoice:
    preference_ref: str
    value_ref: str
    category: str
    allowed_scopes: tuple
    required_capability: str

    def __post_init__(self):
        for value, label in (
            (self.preference_ref, "preference_ref"),
            (self.value_ref, "value_ref"),
            (self.category, "category"),
            (self.required_capability, "required_capability"),
        ):
            _bounded_text(value, label, 200)
        if type(self.allowed_scopes) is not tuple or not self.allowed_scopes:
            raise ValueError("allowed_scopes tuple required")


@dataclass(frozen=True)
class PreferenceCatalog:
    property_id: str
    stay_id: str
    choices: tuple
    subjects: tuple

    def __post_init__(self):
        _bounded_text(self.property_id, "property_id", 120)
        _bounded_text(self.stay_id, "stay_id", 120)
        if type(self.choices) is not tuple or any(type(x) is not PreferenceChoice for x in self.choices):
            raise ValueError("typed preference choices required")
        refs = [(x.preference_ref, x.value_ref) for x in self.choices]
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate catalog choice")
        if type(self.subjects) is not tuple:
            raise ValueError("subjects tuple required")
        keys = [(scope, subject) for scope, subject in self.subjects]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate catalog subject")

    @property
    def catalog_hash(self):
        return digest(self)

    def has_subject(self, scope, subject_id):
        return (scope, subject_id) in set(self.subjects)

    def has_choice(self, preference_ref, value_ref, scope):
        return any(
            x.preference_ref == preference_ref
            and x.value_ref == value_ref
            and scope in x.allowed_scopes
            for x in self.choices
        )

    def values_for(self, preference_ref, scope):
        return tuple(
            x.value_ref for x in self.choices
            if x.preference_ref == preference_ref and scope in x.allowed_scopes
        )


# Deliberately finite. Device-specific command/setpoint logic belongs later in
# deterministic orchestration, not in model-authored preference values.
_CAPABILITY_CHOICES = {
    "climate": (
        ("pref.thermal.feel", "thermal.cooler", ("PERSON", "ROOM", "ZONE", "STAY")),
        ("pref.thermal.feel", "thermal.neutral", ("PERSON", "ROOM", "ZONE", "STAY")),
        ("pref.thermal.feel", "thermal.warmer", ("PERSON", "ROOM", "ZONE", "STAY")),
    ),
    "fan": (
        ("pref.airflow.level", "airflow.low", ("PERSON", "ROOM")),
        ("pref.airflow.level", "airflow.medium", ("PERSON", "ROOM")),
        ("pref.airflow.level", "airflow.high", ("PERSON", "ROOM")),
    ),
    "blind": (
        ("pref.light.blocking", "light.open", ("PERSON", "ROOM")),
        ("pref.light.blocking", "light.filtered", ("PERSON", "ROOM")),
        ("pref.light.blocking", "light.dark", ("PERSON", "ROOM")),
    ),
    "lighting": (
        ("pref.lighting.ambience", "lighting.warm", ("PERSON", "ROOM", "SHARED_SPACE", "STAY")),
        ("pref.lighting.ambience", "lighting.bright", ("PERSON", "ROOM", "SHARED_SPACE", "STAY")),
        ("pref.lighting.ambience", "lighting.dim", ("PERSON", "ROOM", "SHARED_SPACE", "STAY")),
    ),
}


def build_catalog(property_profile, property_twin, stay_profile):
    if type(property_profile) is not PropertyProfile or type(property_twin) is not PropertyTwin:
        raise ValueError("typed property context required")
    if type(stay_profile) is not StayProfile:
        raise ValueError("typed stay profile required")
    if not (
        property_profile.property_id
        == property_twin.property_id
        == stay_profile.property_id
    ):
        raise ValueError("property/stay mismatch")

    choices = []
    for capability in sorted(set(property_twin.capability_refs)):
        for pref_ref, value_ref, scopes in _CAPABILITY_CHOICES.get(capability, ()):
            choices.append(
                PreferenceChoice(pref_ref, value_ref, pref_ref.split(".")[1], tuple(scopes), capability)
            )

    subjects = []
    guest_ids = tuple(sorted(g.guest_id for g in stay_profile.guests))
    for guest_id in guest_ids:
        subjects.append(("PERSON", guest_id))
    for room_id in sorted(property_twin.room_ids):
        subjects.append(("ROOM", room_id))
    for zone_id in sorted(property_twin.zone_ids):
        subjects.append(("ZONE", zone_id))
    for shared_id in sorted(property_profile.shared_space_ids):
        subjects.append(("SHARED_SPACE", shared_id))
    subjects.append(("PROPERTY", property_profile.property_id))
    subjects.append(("STAY", stay_profile.stay_id))

    return PreferenceCatalog(
        property_profile.property_id,
        stay_profile.stay_id,
        tuple(choices),
        tuple(subjects),
    )


@dataclass(frozen=True)
class PreferenceSelection:
    preference_ref: str
    value_ref: str
    scope: str
    subject_id: str

    def __post_init__(self):
        _bounded_text(self.preference_ref, "preference_ref", 200)
        _bounded_text(self.value_ref, "value_ref", 200)
        _bounded_text(self.scope, "scope", 40)
        _bounded_text(self.subject_id, "subject_id", 120)


@dataclass(frozen=True)
class PreferenceInterpretation:
    status: str
    selections: tuple = ()
    candidates: tuple = ()
    clarification: str = ""

    def __post_init__(self):
        if self.status not in INTERPRETATION_STATES:
            raise ValueError("unsupported interpretation status")
        if type(self.selections) is not tuple or any(type(x) is not PreferenceSelection for x in self.selections):
            raise ValueError("typed selections required")
        if type(self.candidates) is not tuple or any(type(x) is not PreferenceSelection for x in self.candidates):
            raise ValueError("typed candidates required")
        if type(self.clarification) is not str or len(self.clarification) > 500:
            raise ValueError("invalid clarification")


def interpretation_contract(catalog, *, scope, subject_id):
    """Closed provider contract for one requested subject/scope."""
    if type(catalog) is not PreferenceCatalog:
        raise ValueError("typed PreferenceCatalog required")
    if not catalog.has_subject(scope, subject_id):
        raise ValueError("scope/subject is not available for this stay")

    return {
        "scope": scope,
        "subject_id": subject_id,
        "catalog_hash": catalog.catalog_hash,
        "allowed_choices": tuple(
            {
                "preference_ref": c.preference_ref,
                "value_ref": c.value_ref,
            }
            for c in catalog.choices
            if scope in c.allowed_scopes
        ),
    }


def interpretation_payload(text, catalog, *, scope, subject_id):
    text = _bounded_text(text, "preference text")
    return {
        "text": text,
        **interpretation_contract(catalog, scope=scope, subject_id=subject_id),
    }


def _selection(raw):
    if type(raw) is not dict or set(raw) != {"preference_ref", "value_ref", "scope", "subject_id"}:
        raise ValueError("selection must contain opaque refs only")
    # Numbers and arbitrary setpoint fields are structurally impossible here.
    return PreferenceSelection(
        raw["preference_ref"],
        raw["value_ref"],
        raw["scope"],
        raw["subject_id"],
    )


def _validate_interpretation_against_allowed(
    raw, *, allowed_choices, requested_scope, requested_subject
):
    if type(raw) is not dict:
        raise ValueError("structured interpretation required")
    if set(raw) != {"status", "selections", "candidates", "clarification"}:
        raise ValueError("unexpected interpretation fields")
    status = raw["status"]
    if status not in INTERPRETATION_STATES:
        raise ValueError("unsupported interpretation status")
    if type(raw["selections"]) is not list or type(raw["candidates"]) is not list:
        raise ValueError("selection/candidate lists required")

    selections = tuple(_selection(x) for x in raw["selections"])
    candidates = tuple(_selection(x) for x in raw["candidates"])
    clarification = raw["clarification"]
    if type(clarification) is not str or len(clarification) > 500:
        raise ValueError("invalid clarification")

    all_items = selections + candidates
    if len(all_items) != len(set(
        (x.preference_ref, x.value_ref, x.scope, x.subject_id) for x in all_items
    )):
        raise ValueError("duplicate interpretation option")

    allowed = set(allowed_choices)
    for item in all_items:
        if (item.scope, item.subject_id) != (requested_scope, requested_subject):
            raise ValueError("model cannot redirect preference scope or subject")
        if (item.preference_ref, item.value_ref) not in allowed:
            raise ValueError("unknown or unsupported preference reference")

    if status == "RESOLVED":
        if not selections or candidates or clarification.strip():
            raise ValueError("RESOLVED requires selections only")
    elif status == "NEEDS_CLARIFICATION":
        if selections or len(candidates) < 2 or not clarification.strip():
            raise ValueError("ambiguity must remain unresolved for human clarification")
    else:
        if selections or candidates:
            raise ValueError("UNSUPPORTED cannot carry proposed preferences")

    return PreferenceInterpretation(status, selections, candidates, clarification.strip())


def validate_interpretation_payload(raw, payload):
    """Validate provider output against the exact closed contract it received."""
    if type(payload) is not dict:
        raise ValueError("bounded interpretation payload required")
    if set(payload) != {"text", "scope", "subject_id", "catalog_hash", "allowed_choices"}:
        raise ValueError("unexpected interpretation payload fields")
    _bounded_text(payload["text"], "preference text")
    _bounded_text(payload["scope"], "scope", 40)
    _bounded_text(payload["subject_id"], "subject_id", 120)
    _bounded_text(payload["catalog_hash"], "catalog_hash", 128)

    raw_choices = payload["allowed_choices"]
    if type(raw_choices) not in (list, tuple):
        raise ValueError("allowed_choices sequence required")
    allowed = []
    for item in raw_choices:
        if type(item) is not dict or set(item) != {"preference_ref", "value_ref"}:
            raise ValueError("opaque allowed choice refs required")
        pref_ref = _bounded_text(item["preference_ref"], "preference_ref", 200)
        value_ref = _bounded_text(item["value_ref"], "value_ref", 200)
        allowed.append((pref_ref, value_ref))
    if len(allowed) != len(set(allowed)):
        raise ValueError("duplicate allowed choice")

    result = _validate_interpretation_against_allowed(
        raw,
        allowed_choices=tuple(allowed),
        requested_scope=payload["scope"],
        requested_subject=payload["subject_id"],
    )
    if not allowed and result.status != "UNSUPPORTED":
        raise ValueError("empty catalog can only be UNSUPPORTED")
    return result


def validate_interpretation(raw, catalog, *, requested_scope, requested_subject):
    if type(catalog) is not PreferenceCatalog:
        raise ValueError("typed PreferenceCatalog required")
    if not catalog.has_subject(requested_scope, requested_subject):
        raise ValueError("scope/subject is not available for this stay")
    allowed = tuple(
        (c.preference_ref, c.value_ref)
        for c in catalog.choices
        if requested_scope in c.allowed_scopes
    )
    return _validate_interpretation_against_allowed(
        raw,
        allowed_choices=allowed,
        requested_scope=requested_scope,
        requested_subject=requested_subject,
    )


def propose_from_provider(text, catalog, *, scope, subject_id, provider):
    """Ask a semantic provider to map text onto the closed catalog.

    The provider never gets authority to create a preference. Its output is accepted
    only after deterministic validation against the exact catalog hash/scope/subject.
    """
    payload = interpretation_payload(text, catalog, scope=scope, subject_id=subject_id)
    response = provider.generate("INTERPRET_STAY_PREFERENCES", payload)
    if type(response) is not dict or "output" not in response:
        raise ValueError("structured provider response required")
    return validate_interpretation(
        response["output"],
        catalog,
        requested_scope=scope,
        requested_subject=subject_id,
    )


def resolved_preferences(interpretation, *, id_prefix="pref"):
    """Convert a resolved proposal into typed stay preferences.

    This is still only a proposal object. Callers decide whether/when to amend StayStore.
    """
    if type(interpretation) is not PreferenceInterpretation or interpretation.status != "RESOLVED":
        raise ValueError("resolved interpretation required")
    _bounded_text(id_prefix, "preference id prefix", 60)
    return tuple(
        ScopedPreference(
            f"{id_prefix}-{index}",
            item.scope,
            item.subject_id,
            item.preference_ref,
            item.value_ref,
            "GUEST",
        )
        for index, item in enumerate(interpretation.selections, 1)
    )
