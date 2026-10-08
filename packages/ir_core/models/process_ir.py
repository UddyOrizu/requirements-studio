"""Process IR v1.1 — mirrors schemas/process-ir.schema.json (docs/02)."""
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import (
    AcId,
    ActId,
    AnyNumber,
    Closed,
    Confidence,
    DateTime,
    Duration,
    EdgeId,
    ElementId,
    EntId,
    ExcId,
    GoalId,
    IdeaId,
    NfrId,
    NodeId,
    NonNegativeNumber,
    PersId,
    ProcId,
    RuleId,
    SlaId,
    SrcId,
    StoryId,
    SuggestionId,
    TermId,
    absent,
)

ElementStatus = Literal["proposed", "confirmed", "rejected", "superseded"]
AutomationHint = Literal["ai_candidate", "deterministic_code", "integration", "human", "unknown"]
HitlMode = Literal["automated", "hitl_review", "human_task", "approval"]
Priority = Literal["must", "should", "could", "wont"]


class DerivedFrom(Closed):
    process_id: str
    version: int


class Process(Closed):
    id: ProcId
    name: Annotated[str, Field(min_length=1)]
    description: str = absent()
    domain: str = absent()
    owner_user_id: str
    status: Literal["draft", "in_review", "ready", "exported"]
    version: Annotated[int, Field(ge=0)]
    updated_at: DateTime
    variant: Literal["as_is", "to_be"]
    idea_id: IdeaId = absent()
    derived_from: DerivedFrom = absent()


class Source(Closed):
    title: str
    kind: Literal["sop", "document", "transcript", "email", "spreadsheet", "recording", "interview_answer",
                  "intake", "suggestion", "manual"]
    authority_weight: Confidence
    uri: str = absent()
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] = absent()
    ingested_at: DateTime = absent()


class Locator(Closed):
    kind: Literal["page", "paragraph", "line_range", "timestamp", "message", "cell", "turn", "suggestion", "none"]
    value: str


class ProvenanceRef(Closed):
    source_id: SrcId
    locator: Locator
    excerpt: Annotated[str, Field(max_length=300)] = absent()
    stance: Literal["supports", "contradicts"]
    extraction_certainty: Confidence
    field: str = absent()


class Meta(Closed):
    status: ElementStatus
    confidence: Confidence
    provenance: list[ProvenanceRef]
    confirmed_by: str = absent()
    notes: str = absent()

    @model_validator(mode="after")
    def _confirmed_needs_confirmed_by(self) -> Self:
        if self.status == "confirmed" and "confirmed_by" not in self.model_fields_set:
            raise ValueError("meta.status 'confirmed' requires confirmed_by")
        return self


class Actor(Closed):
    name: str
    kind: Literal["human_role", "team", "system", "external_party"]
    description: str = absent()
    sme_ids: list[str] = absent()
    meta: Meta


class Attribute(Closed):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    type: Literal["string", "number", "boolean", "date", "datetime", "enum", "document", "reference", "money"]
    required: bool = absent()
    pii: bool = absent()
    enum_values: list[str] = absent()
    description: str = absent()


class Entity(Closed):
    name: str
    description: str = absent()
    attributes: list[Attribute]
    meta: Meta


class Hitl(Closed):
    mode: HitlMode
    actor_id: ActId = absent()
    trigger: Literal["always", "on_exception", "low_confidence", "sample"] = absent()
    criteria: str = absent()
    notes: str = absent()

    @model_validator(mode="after")
    def _mode_requirements(self) -> Self:
        need = {"approval": ("actor_id", "criteria"), "hitl_review": ("actor_id", "trigger")}.get(self.mode, ())
        missing = [f for f in need if f not in self.model_fields_set]
        if missing:
            raise ValueError(f"hitl mode '{self.mode}' requires {', '.join(missing)}")
        return self


class AsIsEffort(Closed):
    minutes_per_case: NonNegativeNumber = absent()
    pain_points: list[str] = absent()


class NodeChange(Closed):
    kind: Literal["automated", "automated_with_review", "new", "modified", "control_added"]
    suggestion_id: SuggestionId
    was: str = absent()


class Node(Closed):
    type: Literal["start", "end", "task", "decision", "wait", "event", "subprocess"]
    name: str
    description: str = absent()
    actor_id: ActId = absent()
    inputs: list[EntId] = absent()
    outputs: list[EntId] = absent()
    rule_ids: list[RuleId] = absent()
    sla_ids: list[SlaId] = absent()
    exception_ids: list[ExcId] = absent()
    automation_hint: AutomationHint = absent()
    subprocess_ref: ProcId = absent()
    outcome: str = absent()
    goal_ids: list[GoalId] = absent()
    system_ids: list[ActId] = absent()
    priority: Priority = absent()
    hitl: Hitl = absent()
    as_is_effort: AsIsEffort = absent()
    change: NodeChange = absent()
    meta: Meta


class EdgeCondition(Closed):
    rule_id: RuleId = absent()
    outcome: str = absent()


class Edge(Closed):
    from_: NodeId = Field(alias="from")
    to: NodeId
    label: str = absent()
    condition: EdgeCondition = absent()
    is_default: bool = absent()
    meta: Meta


class TableRow(Closed):
    when: list[str]
    then: str


class TableLogic(Closed):
    kind: Literal["table"]
    columns: list[str]
    rows: list[TableRow]
    hit_policy: Literal["first", "unique", "priority"] = absent()


class ExpressionLogic(Closed):
    kind: Literal["expression"]
    expression: str


class NaturalLanguageLogic(Closed):
    kind: Literal["natural_language"]
    text: str


RuleLogic = Annotated[TableLogic | ExpressionLogic | NaturalLanguageLogic, Field(discriminator="kind")]


class DecisionRule(Closed):
    name: str
    description: str = absent()
    inputs: list[Annotated[str, Field(pattern=r"^ent_[a-z0-9_]{1,60}\.[a-z][a-z0-9_]*$")]] = absent()
    outcomes: Annotated[list[str], Field(min_length=1)]
    logic: RuleLogic
    meta: Meta


class ExceptionHandling(Closed):
    action: Literal["retry", "escalate", "route_to_node", "terminate", "manual_review", "undefined"]
    target_node_id: NodeId = absent()
    notify_actor_id: ActId = absent()
    max_attempts: Annotated[int, Field(ge=1)] = absent()
    notes: str = absent()


class ExceptionCase(Closed):
    name: str
    trigger: str
    trigger_kind: Literal["condition", "timeout", "system_failure", "data_quality"] = absent()
    timeout: Duration = absent()
    applies_to: Annotated[list[NodeId], Field(min_length=1)]
    handling: ExceptionHandling
    meta: Meta


class BreachAction(Closed):
    action: Literal["notify", "escalate", "route_to_node", "terminate", "undefined"]
    target_node_id: NodeId = absent()
    notify_actor_id: ActId = absent()


class SLA(Closed):
    name: str
    applies_to: Annotated[list[NodeId], Field(min_length=1)]
    duration: Duration
    calendar: Literal["working_days", "calendar_days"] = absent()
    clock_starts: str = absent()
    clock_stops: str = absent()
    breach_action: BreachAction
    meta: Meta


class AcceptanceCriterion(Closed):
    title: str
    applies_to: Annotated[list[ElementId], Field(min_length=1)]
    given: Annotated[list[str], Field(min_length=1)]
    when: Annotated[list[str], Field(min_length=1)]
    then: Annotated[list[str], Field(min_length=1)]
    kind: Literal["happy_path", "edge_case", "negative", "nfr"] = "happy_path"
    meta: Meta


class GlossaryTerm(Closed):
    term: str
    definition: str = absent()
    ambiguous: bool
    meta: Meta


class GoalMetric(Closed):
    name: str
    unit: str = absent()
    baseline: AnyNumber = absent()
    target: AnyNumber = absent()


class Goal(Closed):
    statement: str
    metrics: list[GoalMetric]
    persona_ids: list[PersId] = absent()
    meta: Meta


class Persona(Closed):
    name: str
    description: str = absent()
    actor_id: ActId = absent()
    needs: list[str] = absent()
    meta: Meta


class NFR(Closed):
    category: Literal["volume", "performance", "availability", "security", "privacy", "audit", "compliance",
                      "accessibility", "retention", "usability"]
    statement: str
    measure: str = absent()
    applies_to: list[NodeId]
    meta: Meta


class Scope(Closed):
    in_: list[str] = Field(alias="in")
    out: list[str]
    assumptions: list[str]
    constraints: list[str]
    confirmed_none: list[Literal["decisions", "exceptions", "systems"]]


# ---- Story (derived by M7; never patched) ----

class StoryEdgeCase(Closed):
    ref: ElementId
    title: str
    handling: str


class DataRequirement(Closed):
    entity_id: EntId
    access: Literal["read", "write", "read_write"]
    attributes: list[str]


class StoryDependencies(Closed):
    upstream_story_ids: list[StoryId]
    downstream_story_ids: list[StoryId]
    system_actor_ids: list[ActId]


class StoryOpenQuestion(Closed):
    gap_id: str
    text: str
    severity: Literal["blocking", "major", "minor"]
    status: str
    asked_to: str | None = absent()


class HumanQueue(Closed):
    exception_id: str
    actor_id: str | None


class HumanControl(Closed):
    mode: HitlMode | None
    actor_id: str | None = absent()
    trigger: str | None = absent()
    criteria: str | None = absent()
    queues: list[HumanQueue]


class StoryChange(Closed):
    kind: str = absent()
    suggestion_id: str = absent()
    was: str = absent()
    minutes_saved_per_case: AnyNumber | None = absent()


class Story(Closed):
    title: str
    as_a: ActId
    i_want: str
    so_that: str
    priority: Priority | None
    goal_ids: list[GoalId]
    persona_ids: list[PersId]
    node_ids: Annotated[list[NodeId], Field(min_length=1)]
    ac_ids: list[AcId]
    edge_cases: list[StoryEdgeCase]
    nfr_ids: list[NfrId]
    data_requirements: list[DataRequirement]
    dependencies: StoryDependencies
    open_questions: list[StoryOpenQuestion]
    automation_hint: AutomationHint = absent()
    confidence: Confidence
    dor_status: Literal["ready", "waived", "not_ready"]
    open_gap_ids: list[str] = absent()
    rendered_from_version: int = absent()
    human_control: HumanControl
    change: StoryChange | None


class ProcessIR(Closed):
    ir_version: Literal["1.1"]
    process: Process
    sources: dict[SrcId, Source]
    actors: dict[ActId, Actor]
    entities: dict[EntId, Entity]
    nodes: dict[NodeId, Node]
    edges: dict[EdgeId, Edge]
    decision_rules: dict[RuleId, DecisionRule]
    exceptions: dict[ExcId, ExceptionCase]
    slas: dict[SlaId, SLA]
    acceptance_criteria: dict[AcId, AcceptanceCriterion]
    glossary: dict[TermId, GlossaryTerm]
    goals: dict[GoalId, Goal]
    personas: dict[PersId, Persona]
    nfrs: dict[NfrId, NFR]
    scope: Scope
    stories: dict[StoryId, Story] = absent()

