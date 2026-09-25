"""Adaptive Stay application boundary.

One service owns product commands/read models. UI and MCP are adapters only.
The semantic model may propose preferences; explicit application commands mutate state.
"""
from dataclasses import asdict, dataclass
from threading import RLock
from .audit import data, digest
from .preferences import (
    build_catalog,
    interpretation_payload,
    resolved_preferences,
    validate_interpretation,
)
from .stay import StayStore


def _text(value, label, maximum=2000):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


def _friendly_ref(value):
    return value.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").title()


@dataclass(frozen=True)
class PresentationModel:
    """Alexa+-shaped presentation contract shared by future UI/MCP surfaces."""
    status: str
    headline: str
    speech: str = ""
    supporting_text: str = ""
    suggested_actions: tuple = ()
    mode: str = "INLINE"

    def __post_init__(self):
        for value, label, maximum in (
            (self.status, "presentation status", 80),
            (self.headline, "presentation headline", 240),
            (self.speech, "presentation speech", 1000),
            (self.supporting_text, "presentation supporting_text", 1000),
            (self.mode, "presentation mode", 40),
        ):
            if type(value) is not str or len(value) > maximum:
                raise ValueError(f"invalid {label}")
        if not self.status.strip() or not self.headline.strip():
            raise ValueError("presentation status/headline required")
        if self.mode not in ("INLINE", "FULLSCREEN", "VOICE_ONLY"):
            raise ValueError("unsupported presentation mode")
        if type(self.suggested_actions) is not tuple:
            raise ValueError("suggested_actions tuple required")
        if any(type(x) is not str or not x.strip() or len(x) > 120 for x in self.suggested_actions):
            raise ValueError("invalid suggested action")


@dataclass(frozen=True)
class PreferenceProposal:
    proposal_id: str
    stay_binding: str
    catalog_hash: str
    interpretation: object
    provenance: dict


class AdaptiveStayService:
    """Single application boundary for Adaptive Stay.

    This service deliberately owns no device orchestration yet. Gate E covers property/stay
    read models, bounded preference interpretation, explicit preference application and
    checkout. Dream/shared-resource work remains later gates.
    """

    def __init__(self, store, provider):
        if type(store) is not StayStore:
            raise ValueError("typed StayStore required")
        if not hasattr(provider, "generate"):
            raise ValueError("semantic provider required")
        self.store = store
        self.provider = provider
        self._pending = {}
        self._lock = RLock()

    def _result(self, payload, presentation):
        if type(payload) is not dict or type(presentation) is not PresentationModel:
            raise ValueError("typed application result required")
        return {"data": data(payload), "presentation": data(presentation)}

    def _current(self):
        if self.store.current is None:
            raise ValueError("current stay required")
        return self.store.current

    def _catalog(self):
        current = self._current()
        return build_catalog(
            self.store.property_profile,
            self.store.property_twin,
            current.profile,
        )

    def get_property(self):
        profile = self.store.property_profile
        twin = self.store.property_twin
        return self._result(
            {
                "property": data(profile),
                "twin": data(twin),
                "current_stay_id": self.store.current.profile.stay_id if self.store.current else None,
            },
            PresentationModel(
                "PROPERTY",
                profile.name,
                supporting_text=f"{len(twin.room_ids)} bedrooms · {len(twin.zone_ids)} climate zones",
            ),
        )

    def get_current_stay(self):
        with self._lock:
            if self.store.current is None:
                return self._result(
                    {"status": "NO_STAY", "stay": None},
                    PresentationModel(
                        "NO_STAY",
                        "No active stay",
                        "There is no current stay.",
                        "The property is ready for its next booking.",
                    ),
                )
            current = self.store.current
            profile = current.profile
            return self._result(
                {
                    "status": current.state,
                    "version": current.version,
                    "binding": current.binding,
                    "stay": data(profile),
                    "property_name": self.store.property_profile.name,
                },
                PresentationModel(
                    current.state,
                    f"{self.store.property_profile.name} · {len(profile.guests)} guests",
                    supporting_text=f"{profile.arrival} → {profile.departure}",
                ),
            )

    def get_preference_options(self, scope, subject_id):
        scope = _text(scope, "scope", 40)
        subject_id = _text(subject_id, "subject_id", 120)
        with self._lock:
            catalog = self._catalog()
            if not catalog.has_subject(scope, subject_id):
                raise ValueError("scope/subject is not available for this stay")
            choices = tuple(
                {
                    "preference_ref": c.preference_ref,
                    "value_ref": c.value_ref,
                }
                for c in catalog.choices
                if scope in c.allowed_scopes
            )
            return self._result(
                {
                    "catalog_hash": catalog.catalog_hash,
                    "scope": scope,
                    "subject_id": subject_id,
                    "choices": choices,
                },
                PresentationModel(
                    "PREFERENCE_OPTIONS",
                    "Available preferences",
                    supporting_text=f"{len(choices)} supported choices for this guest or space.",
                ),
            )


    def propose_preference(self, preference_ref, value_ref, scope, subject_id, catalog_hash):
        """Create a deterministic proposal from one closed-catalog client selection.

        This is the public MCP/Alexa path: the intelligent host chooses only from refs
        returned by get_preference_options(). No semantic provider/model call occurs here.
        The stay remains unchanged until a separate authenticated/trusted commit path applies
        the proposal.
        """
        preference_ref = _text(preference_ref, "preference_ref", 200)
        value_ref = _text(value_ref, "value_ref", 200)
        scope = _text(scope, "scope", 40)
        subject_id = _text(subject_id, "subject_id", 120)
        catalog_hash = _text(catalog_hash, "catalog_hash", 128)
        with self._lock:
            current = self._current()
            catalog = self._catalog()
            if catalog.catalog_hash != catalog_hash:
                raise ValueError("stale preference catalog")
            interpretation = validate_interpretation(
                {
                    "status": "RESOLVED",
                    "selections": [{
                        "preference_ref": preference_ref,
                        "value_ref": value_ref,
                        "scope": scope,
                        "subject_id": subject_id,
                    }],
                    "candidates": [],
                    "clarification": "",
                },
                catalog,
                requested_scope=scope,
                requested_subject=subject_id,
            )
            provenance = {
                "kind": "MCP_CLIENT_SELECTION",
                "operation": "PROPOSE_STAY_PREFERENCE",
                "catalog_hash": catalog.catalog_hash,
                "credentials_recorded": False,
            }
            proposal_id = "pp-" + digest((
                current.binding,
                catalog.catalog_hash,
                preference_ref,
                value_ref,
                scope,
                subject_id,
                "MCP_CLIENT_SELECTION",
            ))[:24]
            proposal = PreferenceProposal(
                proposal_id,
                current.binding,
                catalog.catalog_hash,
                interpretation,
                data(provenance),
            )
            self._pending[proposal_id] = proposal
            return self._result(
                {
                    "proposal_id": proposal_id,
                    "status": "RESOLVED",
                    "stay_binding": current.binding,
                    "catalog_hash": catalog.catalog_hash,
                    "selections": tuple(data(x) for x in interpretation.selections),
                    "candidates": (),
                    "clarification": "",
                    "provenance": data(provenance),
                    "state_mutated": False,
                },
                PresentationModel(
                    "RESOLVED",
                    "Preference ready to review",
                    "I understood that preference. Review it before applying.",
                    _friendly_ref(value_ref),
                    ("Apply preference", "Cancel"),
                ),
            )

    def interpret_preference(self, text, scope, subject_id):
        text = _text(text, "preference text")
        scope = _text(scope, "scope", 40)
        subject_id = _text(subject_id, "subject_id", 120)
        with self._lock:
            current = self._current()
            catalog = self._catalog()
            payload = interpretation_payload(
                text, catalog, scope=scope, subject_id=subject_id
            )
            response = self.provider.generate("INTERPRET_STAY_PREFERENCES", payload)
            if type(response) is not dict or "output" not in response:
                raise ValueError("structured provider response required")
            interpretation = validate_interpretation(
                response["output"],
                catalog,
                requested_scope=scope,
                requested_subject=subject_id,
            )
            provenance = response.get("provenance", {})
            if type(provenance) is not dict:
                raise ValueError("provider provenance must be dict")
            proposal_id = "pp-" + digest((
                current.binding,
                catalog.catalog_hash,
                text,
                scope,
                subject_id,
                interpretation,
            ))[:24]
            proposal = PreferenceProposal(
                proposal_id,
                current.binding,
                catalog.catalog_hash,
                interpretation,
                data(provenance),
            )
            self._pending[proposal_id] = proposal

            if interpretation.status == "RESOLVED":
                labels = tuple(_friendly_ref(x.value_ref) for x in interpretation.selections)
                presentation = PresentationModel(
                    "RESOLVED",
                    "Preference ready to review",
                    "I understood that preference. Review it before applying.",
                    ", ".join(labels),
                    ("Apply preference", "Cancel"),
                )
            elif interpretation.status == "NEEDS_CLARIFICATION":
                actions = tuple(_friendly_ref(x.value_ref) for x in interpretation.candidates)
                presentation = PresentationModel(
                    "NEEDS_CLARIFICATION",
                    "One quick question",
                    interpretation.clarification,
                    interpretation.clarification,
                    actions,
                )
            else:
                presentation = PresentationModel(
                    "UNSUPPORTED",
                    "This property can't support that preference",
                    "That preference is not available with this property's current capabilities.",
                    interpretation.clarification,
                )

            return self._result(
                {
                    "proposal_id": proposal_id,
                    "status": interpretation.status,
                    "stay_binding": current.binding,
                    "catalog_hash": catalog.catalog_hash,
                    "selections": tuple(data(x) for x in interpretation.selections),
                    "candidates": tuple(data(x) for x in interpretation.candidates),
                    "clarification": interpretation.clarification,
                    "provenance": data(provenance),
                    "state_mutated": False,
                },
                presentation,
            )

    def apply_preference(self, proposal_id):
        proposal_id = _text(proposal_id, "proposal_id", 120)
        with self._lock:
            proposal = self._pending.get(proposal_id)
            if proposal is None:
                raise ValueError("unknown preference proposal")
            current = self._current()
            if current.binding != proposal.stay_binding:
                raise ValueError("stale preference proposal")
            catalog = self._catalog()
            if catalog.catalog_hash != proposal.catalog_hash:
                raise ValueError("stale preference catalog")
            if proposal.interpretation.status != "RESOLVED":
                raise ValueError("resolved preference proposal required")

            new_preferences = resolved_preferences(
                proposal.interpretation,
                id_prefix="pref-" + proposal_id[3:15],
            )
            existing_ids = {p.preference_id for p in current.profile.preferences}
            if any(p.preference_id in existing_ids for p in new_preferences):
                raise ValueError("preference identity collision")
            amended = self.store.amend(
                preferences=current.profile.preferences + new_preferences
            )
            self._pending.clear()
            return self._result(
                {
                    "status": amended.state,
                    "version": amended.version,
                    "binding": amended.binding,
                    "applied_preferences": tuple(data(x) for x in new_preferences),
                },
                PresentationModel(
                    "APPLIED",
                    "Preference added",
                    "Your stay preference has been added.",
                    suggested_actions=("View stay",),
                ),
            )

    def discard_preference(self, proposal_id):
        proposal_id = _text(proposal_id, "proposal_id", 120)
        with self._lock:
            if proposal_id not in self._pending:
                raise ValueError("unknown preference proposal")
            del self._pending[proposal_id]
            return self._result(
                {"status": "DISCARDED", "proposal_id": proposal_id},
                PresentationModel(
                    "DISCARDED",
                    "Preference not applied",
                    "No changes were made to the stay.",
                ),
            )

    def checkout(self):
        with self._lock:
            receipt = self.store.checkout()
            self._pending.clear()
            return self._result(
                {"status": "CHECKED_OUT", "receipt": data(receipt)},
                PresentationModel(
                    "CHECKED_OUT",
                    "Stay complete",
                    "Checkout is complete. Temporary guest preferences have expired.",
                    "The property is ready for its next stay.",
                ),
            )
