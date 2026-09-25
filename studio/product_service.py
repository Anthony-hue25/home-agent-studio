"""Alexa+-first Adaptive Stay product application service."""
from dataclasses import dataclass
from threading import RLock, Thread
import time

from .application import PresentationModel
from .audit import data, digest
from .preferences import build_catalog
from .shared_resources import assess_shared_resources
from .stay import ScopedPreference, StayStore
from .home_state_gateway import GatewayPrimitive, SimulatedHomeStateGateway
from .stay_blueprint import DreamJobStore, create_blueprint, is_blueprint_current
from .stay_dream import build_strategy_catalog, evaluate_option
from .stay_planner import PlannerResult


def _text(value, label, maximum=240):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


def _friendly(value):
    return value.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").title()


# Gate J3: how many actually-evaluated, actually-FAILED candidates the Dream
# event UI may narrate before the passing one (or before giving up). Bounded
# so "candidate rejected because..." storytelling never grows unbounded on a
# large catalog -- it is a taste of the real search, not the whole log.
REJECTED_CANDIDATE_LIMIT = 2


def _bounded_planner_provenance(raw):
    """Gate J2 runtime provenance: only bounded, non-sensitive metadata about
    which planner backend actually ran a given Dream job -- never prompts,
    chain-of-thought, raw catalog/guest content, or credentials. This is what
    lets a runtime check tell a real Strands/Bedrock invocation apart from
    the deterministic Fixture planner, from the deployed execution itself
    rather than from source or config alone.
    """
    if type(raw) is not dict:
        raise ValueError("planner provenance dict required")
    kind = raw.get("kind")
    backend = "strands" if kind == "LIVE" else "fixture"
    provider = "bedrock" if kind == "LIVE" else "deterministic"
    bounded = {
        "planner_backend": backend,
        "provider": provider,
        "model": raw.get("model"),
        "planner_success": raw.get("success"),
    }
    if kind == "LIVE":
        bounded["bedrock_calls"] = tuple(
            {"http_status": c.get("http_status"), "request_id": c.get("request_id")}
            for c in raw.get("bedrock_calls", ())
        )
        bounded["grounding_calls"] = tuple(raw.get("grounding_calls", ()))
        bounded["strands_version"] = raw.get("strands_version")
        bounded["input_hash"] = raw.get("input_hash")
        bounded["output_hash"] = raw.get("output_hash")
    return bounded


@dataclass(frozen=True)
class PreferenceProposal:
    proposal_id: str
    stay_binding: str
    catalog_hash: str
    preference_ref: str
    value_ref: str
    scope: str
    subject_id: str


class CompleteCatalogPlanner:
    """Deterministic fixture planner for tests/offline demos only."""
    kind = "FIXTURE"

    def plan(self, catalog, assessment):
        return PlannerResult(
            catalog.options,
            {
                "kind": "FIXTURE",
                "provider": "deterministic catalog selector",
                "success": True,
                "authoritative_verdict": False,
                "model_calls": 0,
            },
        )


class AdaptiveStayProductService:
    def __init__(self, store, topology, planner, *, hot_water_state=None, hot_water_requests=()):
        if type(store) is not StayStore:
            raise ValueError("typed StayStore required")
        if not hasattr(topology, "validate_against"):
            raise ValueError("capability topology required")
        if not hasattr(planner, "plan"):
            raise ValueError("bounded strategy planner required")
        topology.validate_against(store.property_twin)
        if type(hot_water_requests) is not tuple:
            raise ValueError("hot_water_requests tuple required")
        self.store = store
        self.topology = topology
        self.planner = planner
        self.hot_water_state = hot_water_state
        self.hot_water_requests = hot_water_requests
        self.jobs = DreamJobStore()
        self._pending = {}
        self._blueprints = {}
        self._job_blueprints = {}
        self._dream_provenance = {}
        self._latest_job_id = ""
        self._latest_blueprint_id = ""
        self._active_blueprint_id = ""
        self._active_profile_hash = ""
        self._active_resource_hash = ""
        self._gateway = SimulatedHomeStateGateway()
        self._lock = RLock()

    def _result(self, payload, presentation):
        return {"data": data(payload), "presentation": data(presentation)}

    def _current(self):
        if self.store.current is None:
            raise ValueError("current stay required")
        return self.store.current

    def _preference_catalog(self):
        current = self._current()
        return build_catalog(
            self.store.property_profile,
            self.store.property_twin,
            current.profile,
        )

    def _assessment(self, current=None):
        current = current or self._current()
        return assess_shared_resources(
            self.store.property_twin,
            current.profile,
            hot_water_state=self.hot_water_state,
            hot_water_requests=self.hot_water_requests,
        )

    def _dream_context(self, current=None):
        current = current or self._current()
        assessment = self._assessment(current)
        catalog = build_strategy_catalog(
            self.store.property_twin,
            self.topology,
            current,
            assessment,
        )
        context_hash = digest((
            current.binding,
            self.topology.binding,
            assessment.binding,
            catalog.catalog_hash,
        ))
        return current, assessment, catalog, context_hash

    def _authorized(self, authorized):
        if authorized is not True:
            return self._result(
                {"status": "AUTH_REQUIRED", "state_mutated": False},
                PresentationModel(
                    "AUTH_REQUIRED",
                    "Sign in to make this change",
                    "This action changes the stay and requires authenticated authority.",
                    "Your current stay has not been changed.",
                ),
            )
        return None

    def get_stay(self):
        with self._lock:
            if self.store.current is None:
                return self._result(
                    {
                        "status": "NO_STAY",
                        "property": data(self.store.property_profile),
                        "stay": None,
                        "dream": None,
                        "blueprint": None,
                    },
                    PresentationModel(
                        "NO_STAY",
                        "Ready for the next stay",
                        "There is no current stay.",
                        "Temporary guest state has been cleared.",
                    ),
                )

            current = self.store.current
            assessment = self._assessment(current)
            assignments = {a.guest_id: a.room_id for a in current.profile.assignments}
            guests = tuple({
                "guest_id": g.guest_id,
                "display_name": g.display_name,
                "group_id": g.group_id,
                "room_id": assignments[g.guest_id],
                "zone_id": self.store.property_twin.zone_for_room(assignments[g.guest_id]),
            } for g in current.profile.guests)
            job = self.jobs.get(self._latest_job_id) if self._latest_job_id else None
            blueprint = self._blueprints.get(self._latest_blueprint_id)
            active_stale = False
            if self._active_blueprint_id:
                active_stale = (
                    digest(current.profile) != self._active_profile_hash
                    or assessment.binding != self._active_resource_hash
                )

            # A Dream can complete and hand back a verified Blueprint that is
            # still current (nothing has changed since) but not yet
            # activated. Without this branch the headline fell through to
            # "ready to Dream" even though the stay had already been Dreamed
            # -- a stale-feeling headline directly under a fresh "Verified
            # Stay Blueprint" card. Reuses the same is_blueprint_current()
            # check get_stay_blueprint() uses; no new verification logic.
            blueprint_ready = False
            if blueprint is not None:
                _dc_current, _dc_assessment, _dc_catalog, _ = self._dream_context(current)
                blueprint_ready = is_blueprint_current(
                    blueprint, self.store.property_twin, self.topology,
                    _dc_current, _dc_assessment, _dc_catalog,
                )
            if current.state == "ACTIVE":
                headline = f"{self.store.property_profile.name} is adapting to this stay"
                speech = "Your stay is active."
            elif assessment.status == "CONFLICT":
                headline = "This stay needs coordination"
                speech = "Some individually valid preferences share the same physical resources."
            elif blueprint_ready:
                headline = "Your stay is verified and ready to activate"
                speech = "I found a configuration that passed Dream. Nothing is active until you say so."
            elif current.profile.preferences:
                headline = "Your stay is ready to Dream"
                speech = "I can rehearse this stay before anything is activated."
            else:
                headline = f"Your stay at {self.store.property_profile.name} is ready"
                speech = "Tell me how you want the stay to feel."

            return self._result(
                {
                    "status": current.state,
                    "version": current.version,
                    "binding": current.binding,
                    "property": data(self.store.property_profile),
                    "twin": data(self.store.property_twin),
                    "stay": data(current.profile),
                    "guests": guests,
                    "shared_resources": data(assessment),
                    # Presentation-only addition: the service already holds each
                    # simulated hot-water request's owning guest; earlier Gate I
                    # surfaced only aggregate counts, hiding who a hot-water
                    # conflict actually involves. This does not change shared
                    # resource semantics or any MCP tool contract.
                    "hot_water_requests": tuple(
                        {"request_id": r.request_id, "subject_id": r.subject_id}
                        for r in self.hot_water_requests
                    ),
                    "dream": data(job) if job else None,
                    "blueprint": data(blueprint) if blueprint else None,
                    "active_blueprint_id": self._active_blueprint_id or None,
                    "active_blueprint_stale": active_stale,
                },
                PresentationModel(
                    current.state,
                    headline,
                    speech,
                    f"{len(current.profile.guests)} guests · {len(self.store.property_twin.room_ids)} bedrooms",
                    ("Personalize stay", "Dream this stay") if current.profile.preferences else ("Personalize stay",),
                ),
            )

    def get_preference_options(self, scope, subject_id):
        scope = _text(scope, "scope", 40)
        subject_id = _text(subject_id, "subject_id", 160)
        with self._lock:
            catalog = self._preference_catalog()
            if not catalog.has_subject(scope, subject_id):
                raise ValueError("scope/subject is not available for this stay")
            choices = tuple({
                "preference_ref": c.preference_ref,
                "value_ref": c.value_ref,
            } for c in catalog.choices if scope in c.allowed_scopes)
            return self._result(
                {
                    "catalog_hash": catalog.catalog_hash,
                    "scope": scope,
                    "subject_id": subject_id,
                    "choices": choices,
                },
                PresentationModel(
                    "PREFERENCE_OPTIONS",
                    "What should feel different?",
                    supporting_text=f"{len(choices)} choices this property can actually support.",
                ),
            )

    def propose_preference(self, preference_ref, value_ref, scope, subject_id, catalog_hash):
        preference_ref = _text(preference_ref, "preference_ref")
        value_ref = _text(value_ref, "value_ref")
        scope = _text(scope, "scope", 40)
        subject_id = _text(subject_id, "subject_id", 160)
        catalog_hash = _text(catalog_hash, "catalog_hash")
        with self._lock:
            current = self._current()
            catalog = self._preference_catalog()
            if catalog.catalog_hash != catalog_hash:
                raise ValueError("stale preference catalog")
            if not catalog.has_subject(scope, subject_id):
                raise ValueError("scope/subject is not available for this stay")
            if not catalog.has_choice(preference_ref, value_ref, scope):
                raise ValueError("preference/value is not in the closed catalog")
            proposal_id = "pp-" + digest((
                current.binding, catalog_hash, preference_ref, value_ref, scope, subject_id
            ))[:24]
            proposal = PreferenceProposal(
                proposal_id, current.binding, catalog_hash,
                preference_ref, value_ref, scope, subject_id,
            )
            self._pending[proposal_id] = proposal
            return self._result(
                {
                    "status": "PROPOSED",
                    "proposal_id": proposal_id,
                    "preference_ref": preference_ref,
                    "value_ref": value_ref,
                    "scope": scope,
                    "subject_id": subject_id,
                    "state_mutated": False,
                },
                PresentationModel(
                    "PROPOSED",
                    f"I can make that feel {_friendly(value_ref).lower()}",
                    "Review the preference before adding it to this stay.",
                    "Nothing has changed yet.",
                    ("Add to stay", "Cancel"),
                ),
            )

    def change_stay(self, proposal_id, *, authorized=False):
        denied = self._authorized(authorized)
        if denied:
            return denied
        proposal_id = _text(proposal_id, "proposal_id")
        with self._lock:
            proposal = self._pending.get(proposal_id)
            if proposal is None:
                raise ValueError("unknown preference proposal")
            current = self._current()
            if current.binding != proposal.stay_binding:
                raise ValueError("stale preference proposal")
            catalog = self._preference_catalog()
            if catalog.catalog_hash != proposal.catalog_hash:
                raise ValueError("stale preference catalog")
            if not catalog.has_choice(proposal.preference_ref, proposal.value_ref, proposal.scope):
                raise ValueError("proposal no longer belongs to closed catalog")
            pref_id = "pref-" + digest((
                proposal_id, proposal.preference_ref, proposal.value_ref,
                proposal.scope, proposal.subject_id
            ))[:20]
            preference = ScopedPreference(
                pref_id, proposal.scope, proposal.subject_id,
                proposal.preference_ref, proposal.value_ref, "GUEST",
            )
            amended = self.store.amend(
                preferences=current.profile.preferences + (preference,)
            )
            self._pending.clear()
            self._latest_job_id = ""
            self._latest_blueprint_id = ""
            return self._result(
                {
                    "status": amended.state,
                    "version": amended.version,
                    "binding": amended.binding,
                    "applied_preference": data(preference),
                    "requires_new_dream": True,
                },
                PresentationModel(
                    "CHANGED",
                    "Preference added to this stay",
                    "The stay changed. Dream it again before activation.",
                    suggested_actions=("Dream this stay",),
                ),
            )

    def dream_stay(self):
        """Request Dream and return immediately; model inference runs off the MCP fast path."""
        with self._lock:
            current, assessment, catalog, context_hash = self._dream_context()
            if self._latest_job_id:
                existing = self.jobs.get(self._latest_job_id)
                if existing and existing.context_hash == context_hash and existing.status in ("REQUESTED", "RUNNING", "READY"):
                    mapped = self._job_blueprints.get(existing.job_id)
                    if mapped:
                        self._latest_blueprint_id = mapped
                    return self._dream_response(existing)

            # The job id is deterministic (derived from context_hash), so an
            # identical stay configuration dreamed earlier in this service's
            # lifetime -- even long ago, under a since-cleared "latest job"
            # pointer -- is found and reused here rather than re-run. Adopting
            # that job as the new "latest" without also restoring the
            # blueprint it already produced left _latest_blueprint_id pointing
            # nowhere: get_dream_status()/dream_stay() would keep reporting
            # this job READY with a real blueprint_id, yet get_stay_blueprint()
            # (which defaults to _latest_blueprint_id) raised "Stay Blueprint
            # is not ready". Restoring it here keeps both pointers consistent.
            job_id = "dream-" + context_hash[:24]
            existing = self.jobs.get(job_id)
            if existing is not None:
                self._latest_job_id = job_id
                mapped = self._job_blueprints.get(job_id)
                if mapped:
                    self._latest_blueprint_id = mapped
                return self._dream_response(existing)
            job = self.jobs.request(job_id, context_hash)
            self._latest_job_id = job_id
            Thread(
                target=self._run_dream,
                args=(job_id, current, assessment, catalog),
                name=f"adaptive-stay-{job_id}",
                daemon=True,
            ).start()
            return self._dream_response(job)

    def _dream_response(self, job):
        actions = ("Check Dream",)
        if job.status == "READY":
            actions = ("View Stay Blueprint",)
        return self._result(
            {
                "job_id": job.job_id,
                "status": job.status,
                "context_hash": job.context_hash,
                "blueprint_id": self._job_blueprints.get(job.job_id),
                "planner_provenance": self._dream_provenance.get(job.job_id),
            },
            PresentationModel(
                job.status,
                "Dreaming this stay..." if job.status in ("REQUESTED", "RUNNING") else (
                    "Stay Blueprint ready" if job.status == "READY" else "Dream needs attention"
                ),
                "I am rehearsing candidate configurations against the property." if job.status in ("REQUESTED", "RUNNING")
                else ("A configuration passed deterministic Dream." if job.status == "READY" else "No verified configuration is ready."),
                suggested_actions=actions,
            ),
        )

    def _run_dream(self, job_id, current, assessment, catalog):
        # Gate J2 runtime provenance for this one Dream job -- bounded metadata
        # only (see _bounded_planner_provenance). Recorded incrementally so a
        # failed Live attempt is still visible as an attempted "strands"/
        # "bedrock" run rather than silently looking like nothing happened.
        provenance = {"planner_backend": "strands" if getattr(self.planner, "kind", "") == "LIVE" else "fixture"}
        try:
            self.jobs.start(job_id)
            planned = self.planner.plan(catalog, assessment)
            if type(planned) is not PlannerResult:
                raise ValueError("typed PlannerResult required")
            provenance = _bounded_planner_provenance(planned.provenance)
            with self._lock:
                self._dream_provenance[job_id] = dict(provenance)
            passing = None
            selected_refs = set()
            # Bounded, real-evaluation-only candidate narration for the Dream
            # UI: at most REJECTED_CANDIDATE_LIMIT actual FAILED DreamEvaluations
            # encountered before (or instead of) the passing one, each carrying
            # only its own real unresolved reason codes. Never fabricated, never
            # padded past what Dream actually evaluated.
            rejected = []
            for option in planned.options:
                selected_refs.add(option.option_ref)
                dream = evaluate_option(
                    self.store.property_twin, self.topology, current,
                    assessment, catalog, option.option_ref,
                )
                if dream.status == "PASS":
                    if passing is None:
                        passing = (option, dream)
                elif passing is None and len(rejected) < REJECTED_CANDIDATE_LIMIT:
                    rejected.append(dream)

            # The deterministic strategy catalog is deliberately bounded. If a
            # live planner-selected subset misses a valid option, Dream completes
            # coverage of the remaining already-authorized catalog. No new
            # strategy is invented and the model still never grades itself.
            if passing is None:
                for option in catalog.options:
                    if option.option_ref in selected_refs:
                        continue
                    dream = evaluate_option(
                        self.store.property_twin, self.topology, current,
                        assessment, catalog, option.option_ref,
                    )
                    if dream.status == "PASS":
                        passing = (option, dream)
                        break
                    elif len(rejected) < REJECTED_CANDIDATE_LIMIT:
                        rejected.append(dream)

            provenance["rejected_candidates"] = tuple(
                {"option_ref": d.option_ref, "unresolved": d.unresolved} for d in rejected
            )
            if passing is None:
                provenance["deterministic_verification"] = {"status": "FAIL", "unresolved_count": None}
                with self._lock:
                    self._dream_provenance[job_id] = dict(provenance)
                self.jobs.fail(job_id, "NO_VERIFIED_STRATEGY")
                return
            option, dream = passing
            provenance["deterministic_verification"] = {
                "status": dream.status,
                "option_ref": dream.option_ref,
                "unresolved_count": len(dream.unresolved),
            }
            blueprint_id = "bp-" + digest((job_id, option.option_ref, dream.binding))[:24]
            blueprint = create_blueprint(
                blueprint_id, self.store.property_twin, self.topology,
                current, assessment, catalog, option, dream,
            )
            provenance["blueprint_id"] = blueprint_id
            with self._lock:
                self._blueprints[blueprint_id] = blueprint
                self._job_blueprints[job_id] = blueprint_id
                self._latest_blueprint_id = blueprint_id
                self._dream_provenance[job_id] = dict(provenance)
                self._dream_provenance[blueprint_id] = self._dream_provenance[job_id]
                self.jobs.complete(job_id, blueprint)
        except Exception as exc:
            provenance["planner_success"] = False
            provenance["error_type"] = type(exc).__name__
            with self._lock:
                self._dream_provenance[job_id] = dict(provenance)
            try:
                self.jobs.fail(job_id, type(exc).__name__.upper())
            except Exception:
                pass

    def get_dream_status(self, job_id):
        job_id = _text(job_id, "job_id")
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise ValueError("unknown Dream job")
            return self._dream_response(job)

    def get_stay_blueprint(self, blueprint_id=""):
        with self._lock:
            blueprint_id = blueprint_id.strip() if type(blueprint_id) is str else ""
            blueprint_id = blueprint_id or self._latest_blueprint_id
            if not blueprint_id or blueprint_id not in self._blueprints:
                raise ValueError("Stay Blueprint is not ready")
            blueprint = self._blueprints[blueprint_id]
            current, assessment, catalog, _ = self._dream_context()
            is_current = is_blueprint_current(
                blueprint, self.store.property_twin, self.topology,
                current, assessment, catalog,
            )
            option = catalog.option(blueprint.option_ref)
            primitives = tuple(data(catalog.primitive(ref)) for ref in option.primitive_refs) if option else ()
            if option is None:
                is_current = False
            return self._result(
                {
                    "blueprint": data(blueprint),
                    "is_current": is_current,
                    "primitives": primitives,
                    "activation_authorized": False,
                    "planner_provenance": self._dream_provenance.get(blueprint_id),
                },
                PresentationModel(
                    "BLUEPRINT",
                    "Stay Blueprint",
                    "This configuration passed deterministic Dream.",
                    "Review it before activation.",
                    ("Activate stay", "View Dream"),
                    mode="FULLSCREEN",
                ),
            )

    def activate_stay(self, blueprint_id, *, authorized=False):
        denied = self._authorized(authorized)
        if denied:
            return denied
        blueprint_id = _text(blueprint_id, "blueprint_id")
        with self._lock:
            blueprint = self._blueprints.get(blueprint_id)
            if blueprint is None:
                raise ValueError("unknown Stay Blueprint")
            current, assessment, catalog, _ = self._dream_context()
            if not is_blueprint_current(
                blueprint, self.store.property_twin, self.topology,
                current, assessment, catalog,
            ):
                raise ValueError("stale Stay Blueprint")
            # Gate J2 execution/readback proof: the exact authorized
            # configuration (this Blueprint's option, expanded to its
            # concrete primitives) is applied to the simulated Home State
            # Gateway boundary, then independently read back and compared.
            # Only an exact match may report activation as successful --
            # anything else fails closed, before any stay/session state is
            # mutated below.
            option = catalog.option(blueprint.option_ref)
            if option is None:
                raise ValueError("stale Stay Blueprint")
            gateway_primitives = tuple(
                GatewayPrimitive(
                    catalog.primitive(ref).kind,
                    catalog.primitive(ref).target_id,
                    catalog.primitive(ref).value_ref,
                )
                for ref in option.primitive_refs
            )
            gateway_status, gateway_detail = self._gateway.apply_and_verify(
                blueprint.binding, gateway_primitives,
            )
            if gateway_status != "VERIFIED_ACTIVE":
                provenance = self._dream_provenance.get(blueprint_id)
                if provenance is not None:
                    provenance["execution_result"] = gateway_status
                raise ValueError("Home State Gateway readback verification failed")

            applied_profile_hash = digest(current.profile)
            applied_resource_hash = assessment.binding
            if current.state == "BOOKED":
                current = self.store.activate()
            elif current.state != "ACTIVE":
                raise ValueError("unsupported stay state for activation")
            self._active_blueprint_id = blueprint_id
            self._active_profile_hash = applied_profile_hash
            self._active_resource_hash = applied_resource_hash
            provenance = self._dream_provenance.get(blueprint_id)
            if provenance is not None:
                provenance["execution_result"] = gateway_status
                provenance["gateway_primitive_count"] = gateway_detail.get("primitive_count")
            return self._result(
                {
                    "status": "ACTIVE",
                    "stay_version": current.version,
                    "blueprint_id": blueprint_id,
                    "blueprint_binding": blueprint.binding,
                    "device_execution": "SIMULATED_HOME_STATE_GATEWAY",
                    "execution_result": gateway_status,
                },
                PresentationModel(
                    "ACTIVE",
                    "Your stay is active",
                    "The verified Stay Blueprint is now the active configuration.",
                    "Physical device execution remains simulated in this build.",
                    ("Change something", "View Stay Blueprint"),
                ),
            )

    def checkout_stay(self, *, authorized=False):
        denied = self._authorized(authorized)
        if denied:
            return denied
        with self._lock:
            receipt = self.store.checkout()
            self._pending.clear()
            self._blueprints.clear()
            self._job_blueprints.clear()
            self._dream_provenance.clear()
            # Fresh simulated Home State Gateway per stay: a checked-out
            # stay's applied physical state (and idempotency ledger) must
            # not leak into whatever stay/property comes next.
            self._gateway = SimulatedHomeStateGateway()
            # A checked-out stay's Dream job history must not survive into the
            # next stay. Dream job identity is deterministic (derived only from
            # a content hash of the stay/preference/resource context), so if a
            # later stay happens to reproduce the exact same context (e.g. the
            # same demo/lab scenario loaded twice back to back), an uncleared
            # self.jobs would resurface the old job's terminal READY status
            # with none of its blueprint bookkeeping (that was just cleared
            # above) -- a stale, permanently-unusable "READY" Dream job that
            # get_stay_blueprint can never resolve. Resetting the job store on
            # checkout is what makes "zero cross-stay leakage" true for Dream
            # state as well as for guest/preference state.
            self.jobs = DreamJobStore()
            self._latest_job_id = ""
            self._latest_blueprint_id = ""
            self._active_blueprint_id = ""
            self._active_profile_hash = ""
            self._active_resource_hash = ""
            return self._result(
                {"status": "CHECKED_OUT", "receipt": data(receipt)},
                PresentationModel(
                    "CHECKED_OUT",
                    "Checkout complete",
                    "Temporary guest state has expired.",
                    "The property is ready for its next stay.",
                ),
            )

    def wait_for_job(self, job_id, timeout=10):
        """Test/demo helper. Public MCP never blocks on this."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.jobs.get(job_id)
            if job and job.status in ("READY", "FAILED"):
                return job
            time.sleep(.02)
        raise TimeoutError("Dream job did not finish")
