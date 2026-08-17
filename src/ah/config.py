from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any
import tomllib


def _path(base: Path, value: str | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    # Preserve Windows absolute paths even when config is inspected on another OS.
    if PureWindowsPath(raw).is_absolute():
        return Path(raw)
    return (base / p).resolve()


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    raw = data.get(name, {})
    if not isinstance(raw, dict):
        raise ValueError(f"config section [{name}] must be a table")
    return raw


@dataclass(frozen=True, slots=True)
class PathsConfig:
    project_dir: Path
    llm_model_dir: Path | None
    tokenizer_dir: Path | None
    adapter_dir: Path | None
    system_prompt_path: Path | None
    agent_prompt_path: Path | None
    perception_prompt_path: Path | None
    perception_prompt_dir: Path | None
    data_dir: Path
    persistence_file: Path
    logs_dir: Path


@dataclass(frozen=True, slots=True)
class LLMRoleSettings:
    max_new_tokens: int = 256
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 0
    repetition_penalty: float = 1.0
    no_repeat_ngram_size: int = 0
    use_cache: bool = True

    def __post_init__(self) -> None:
        if self.max_new_tokens <= 0:
            raise ValueError("LLM role max_new_tokens must be > 0")
        if self.temperature < 0:
            raise ValueError("LLM role temperature must be >= 0")
        if not 0 < self.top_p <= 1:
            raise ValueError("LLM role top_p must be in (0, 1]")
        if self.top_k < 0:
            raise ValueError("LLM role top_k must be >= 0")
        if self.repetition_penalty <= 0:
            raise ValueError("LLM role repetition_penalty must be > 0")
        if self.no_repeat_ngram_size < 0:
            raise ValueError("LLM role no_repeat_ngram_size must be >= 0")


@dataclass(frozen=True, slots=True)
class LLMConfig:
    enabled: bool = True
    backend: str = "builtin_process"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    loader_type: str = "auto"
    device_map: str = "auto"
    dtype: str = "auto"
    local_files_only: bool = True
    trust_remote_code: bool = True
    use_4bit: bool = False
    ctx_total: int = 0
    max_new_tokens: int = 256
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 40
    repetition_penalty: float = 1.05
    no_repeat_ngram_size: int = 0
    enable_thinking: bool = False
    strip_thinking: bool = True
    startup_timeout_seconds: float = 180.0
    request_timeout_seconds: float = 240.0
    engine_script: Path | None = None
    history_messages: int = 0
    perception_protocol: str = "adaptive_v3"
    perception_probe_retry_attempts: int = 1
    perception_ground_actants: bool = True
    perception_max_acts: int = 4
    perception_max_actants_per_act: int = 8
    perception_predicate_symbol_language: str = "en"
    perception_morphology_backend: str = "auto"
    perception: LLMRoleSettings = field(default_factory=lambda: LLMRoleSettings(max_new_tokens=192, temperature=0.0, top_p=1.0, top_k=0, repetition_penalty=1.0, no_repeat_ngram_size=0))
    agent_repair_attempts: int = 1
    agent_sanitize_context_echo: bool = True
    agent: LLMRoleSettings = field(default_factory=lambda: LLMRoleSettings(max_new_tokens=384, temperature=0.2, top_p=0.9, top_k=40, repetition_penalty=1.05, no_repeat_ngram_size=0))

    @property
    def perception_repair_attempts(self) -> int:
        """Deprecated compatibility alias for pre-adaptive configs/callers."""
        return self.perception_probe_retry_attempts

    def __post_init__(self) -> None:
        if self.ctx_total < 0:
            raise ValueError("llm.ctx_total must be >= 0")
        if self.max_new_tokens <= 0:
            raise ValueError("llm.max_new_tokens must be > 0")
        if self.temperature < 0:
            raise ValueError("llm.temperature must be >= 0")
        if not 0 < self.top_p <= 1:
            raise ValueError("llm.top_p must be in (0, 1]")
        if self.top_k < 0:
            raise ValueError("llm.top_k must be >= 0")
        if self.history_messages != 0:
            raise ValueError("llm.history_messages currently must be 0 (stateless mechanical requests)")
        if self.perception_protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3", "span_v1", "line_v1", "compact_json_v1", "legacy_json"}:
            raise ValueError("llm.perception.protocol must be adaptive_v3/adaptive_v2/adaptive_v1 or a legacy protocol")
        if self.perception_probe_retry_attempts < 0 or self.perception_probe_retry_attempts > 2:
            raise ValueError("llm.perception.probe_retry_attempts must be in [0, 2]")
        if self.perception_max_acts <= 0 or self.perception_max_acts > 16:
            raise ValueError("llm.perception.max_acts must be in [1, 16]")
        if self.perception_max_actants_per_act <= 0 or self.perception_max_actants_per_act > 32:
            raise ValueError("llm.perception.max_actants_per_act must be in [1, 32]")
        if self.perception_predicate_symbol_language != "en":
            raise ValueError("llm.perception.predicate_symbol_language currently must be 'en'")
        if self.perception_morphology_backend not in {"auto", "pymorphy3", "none"}:
            raise ValueError("llm.perception.morphology_backend must be auto, pymorphy3, or none")
        if self.agent_repair_attempts < 0 or self.agent_repair_attempts > 2:
            raise ValueError("llm.agent.repair_attempts must be in [0, 2]")
        if self.backend not in {"builtin_process", "ollama"}:
            raise ValueError("llm.backend must be builtin_process or ollama")
        if not str(self.ollama_base_url).strip():
            raise ValueError("llm.ollama_base_url must not be empty")


@dataclass(frozen=True, slots=True)
class IntegrationSettings:
    initial_hypernode_weight: float = 0.4
    experience_hypernode_weight: float = 0.3
    follow_link_weight: float = 0.2
    cause_link_weight: float = 0.2
    initial_inferred_link_weight: float = 0.25

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_hypernode_weight", self.initial_hypernode_weight),
            ("experience_hypernode_weight", self.experience_hypernode_weight),
            ("follow_link_weight", self.follow_link_weight),
            ("cause_link_weight", self.cause_link_weight),
            ("initial_inferred_link_weight", self.initial_inferred_link_weight),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"integration.{name} must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class ActivationSettings:
    kind: str = "additive_clamp"
    gain: float = 1.0
    epsilon: float = 1e-9

    def __post_init__(self) -> None:
        if self.kind not in {"additive_clamp", "saturating_additive"}:
            raise ValueError("ignition.activation.kind must be additive_clamp or saturating_additive")
        if self.gain < 0:
            raise ValueError("ignition.activation.gain must be >= 0")
        if self.epsilon <= 0:
            raise ValueError("ignition.activation.epsilon must be > 0")


@dataclass(frozen=True, slots=True)
class DecaySettings:
    kind: str = "sigmoid_epoch"
    alpha: float = 0.60
    midpoint_ticks: float = 12.0
    steepness: float = 0.35
    half_life_ticks: float = 12.0
    reactivation_reset_ratio: float = 1.0
    reactivation_min_input: float = 0.05

    def __post_init__(self) -> None:
        if self.kind not in {"sigmoid_epoch", "exponential_epoch"}:
            raise ValueError("ignition.decay.kind must be sigmoid_epoch or exponential_epoch")
        if not 0 <= self.alpha < 1:
            raise ValueError("ignition.decay.alpha must be in [0, 1)")
        if self.midpoint_ticks <= 0:
            raise ValueError("ignition.decay.midpoint_ticks must be > 0")
        if self.steepness <= 0:
            raise ValueError("ignition.decay.steepness must be > 0")
        if self.half_life_ticks <= 0:
            raise ValueError("ignition.decay.half_life_ticks must be > 0")
        if self.reactivation_reset_ratio < 0:
            raise ValueError("ignition.decay.reactivation_reset_ratio must be >= 0")
        if self.reactivation_min_input < 0:
            raise ValueError("ignition.decay.reactivation_min_input must be >= 0")


@dataclass(frozen=True, slots=True)
class PlasticitySettings:
    enabled: bool = True
    link_kind: str = "additive_hebb"
    hypernode_kind: str = "additive_confirmation_refutation"
    link_hebb_increment: float = 0.015
    link_async_decrement: float = 0.002
    link_weight_floor: float = 0.02
    ignore_pacemaker_only_events: bool = True
    hypernode_confirmation_increment: float = 0.01
    hypernode_refutation_decrement: float = 0.15

    def __post_init__(self) -> None:
        if self.link_kind not in {"additive_hebb"}:
            raise ValueError("ignition.plasticity.link_kind must be additive_hebb")
        if self.hypernode_kind not in {"additive_confirmation_refutation"}:
            raise ValueError("ignition.plasticity.hypernode_kind must be additive_confirmation_refutation")
        if not 0 <= self.link_weight_floor <= 1:
            raise ValueError("ignition.plasticity.link_weight_floor must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class SeedSettings:
    new_fact: float = 0.65
    reactivated_fact: float = 0.55
    experience: float = 0.5
    # Pre-semantic lexical candidate stimulation; homographs may all receive it.
    sensory_symbol: float = 0.85
    # Strong post-perception stimulation of the canonical S actually resolved
    # in the external prompt, including S created during this same turn.
    resolved_symbol: float = 0.95
    # Runtime relational/query recall anchor. It is attention, not proof and not
    # an h_N confirmation event.
    query_recall: float = 0.80
    correction: float = 0.65
    pacemaker: float = 0.08


@dataclass(frozen=True, slots=True)
class PacemakerSettings:
    enabled: bool = True
    target_policy: str = "round_robin"
    include_symbols: bool = True
    domains: tuple[str, ...] = ("C", "P", "H")
    random_seed: int = 0

    def __post_init__(self) -> None:
        if self.target_policy not in {"round_robin", "random", "workspace", "active"}:
            raise ValueError("ignition.pacemaker.target_policy is invalid")
        allowed = {"C", "P", "H"}
        if any(domain not in allowed for domain in self.domains):
            raise ValueError("ignition.pacemaker.domains must contain only C/P/H")


@dataclass(frozen=True, slots=True)
class IgnitionSettings:
    tick_interval_seconds: float = 1.0
    nu: float = 1.0
    x_max: float = 1.0
    activation: ActivationSettings = field(default_factory=ActivationSettings)
    decay: DecaySettings = field(default_factory=DecaySettings)
    plasticity: PlasticitySettings = field(default_factory=PlasticitySettings)
    seeds: SeedSettings = field(default_factory=SeedSettings)
    pacemaker: PacemakerSettings = field(default_factory=PacemakerSettings)

    def __post_init__(self) -> None:
        if self.tick_interval_seconds <= 0:
            raise ValueError("ignition.tick_interval_seconds must be > 0")
        if self.nu <= 0:
            raise ValueError("ignition.nu must be > 0")
        if self.x_max <= 0:
            raise ValueError("ignition.x_max must be > 0")


@dataclass(frozen=True, slots=True)
class WorkspaceSettings:
    threshold: float = 0.35

    def __post_init__(self) -> None:
        if self.threshold < 0:
            raise ValueError("workspace.threshold must be >= 0")


@dataclass(frozen=True, slots=True)
class LifecycleSettings:
    initial_lifetime_ticks: int = 200
    reinforced_lifetime_ticks: int = 1000
    min_spacing_1_ticks: int = 20
    min_spacing_2_ticks: int = 50
    gc_enabled: bool = True
    orphan_cleanup: bool = True

    def __post_init__(self) -> None:
        if self.initial_lifetime_ticks < 1:
            raise ValueError("lifecycle.initial_lifetime_ticks must be >= 1")
        if self.reinforced_lifetime_ticks < 1:
            raise ValueError("lifecycle.reinforced_lifetime_ticks must be >= 1")
        if self.min_spacing_1_ticks < 1 or self.min_spacing_2_ticks < 1:
            raise ValueError("lifecycle spacing must be >= 1 tick")


@dataclass(frozen=True, slots=True)
class InferenceSettings:
    max_depth: int = 6
    max_expanded_states: int = 5000

    def __post_init__(self) -> None:
        if self.max_depth < 1:
            raise ValueError("inference.max_depth must be >= 1")
        if self.max_expanded_states < 1:
            raise ValueError("inference.max_expanded_states must be >= 1")


@dataclass(frozen=True, slots=True)
class ContextSettings:
    max_tokens: int = 8192
    include_structural_uids: bool = True
    include_mt: bool = False
    max_dependency_depth: int = 8
    overflow_policy: str = "error"

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("context.max_tokens must be > 0")
        if self.max_dependency_depth < 1:
            raise ValueError("context.max_dependency_depth must be >= 1")
        if self.overflow_policy not in {"error"}:
            raise ValueError("context.overflow_policy currently supports only 'error'")


@dataclass(frozen=True, slots=True)
class PersistenceSettings:
    enabled: bool = True
    load_on_start: bool = True
    autosave_every_ticks: int = 200
    save_runtime_state: bool = True
    save_pending_impulses: bool = True

    def __post_init__(self) -> None:
        if self.autosave_every_ticks < 1:
            raise ValueError("persistence.autosave_every_ticks must be >= 1")


@dataclass(frozen=True, slots=True)
class IdentitySettings:
    agent_name: str = "АГент"
    user_name: str = "Пользователь"

    def __post_init__(self) -> None:
        if not self.agent_name.strip() or not self.user_name.strip():
            raise ValueError("identity names must be non-empty")


@dataclass(frozen=True, slots=True)
class GUISettings:
    refresh_hz: int = 30
    render_mode: str = "2.5d"
    show_labels: bool = True
    max_labels: int = 120
    node_size_min: float = 7.0
    node_size_max: float = 24.0
    domain_z_spacing: float = 5.0
    excitation_gamma: float = 0.7
    propagation_duration_seconds: float = 0.9
    show_structural_edges: bool = True
    show_relation_edges: bool = True
    hover_enabled: bool = True
    hover_pick_hz: int = 30
    focus_line_width: float = 3.0
    focus_node_scale: float = 1.35
    focus_neighbor_scale: float = 1.18
    edge_pick_radius_px: float = 8.0
    propagation_cycles_per_second: float = 1.25
    propagation_tail_points: int = 4
    propagation_tail_spacing: float = 0.055
    propagation_edge_width: float = 2.4

    def __post_init__(self) -> None:
        if self.refresh_hz < 1:
            raise ValueError("gui.refresh_hz must be >= 1")
        if self.render_mode not in {"2.5d", "3d"}:
            raise ValueError("gui.render_mode must be '2.5d' or '3d'")
        if self.max_labels < 0:
            raise ValueError("gui.max_labels must be >= 0")
        if self.node_size_min <= 0 or self.node_size_max < self.node_size_min:
            raise ValueError("gui node sizes are invalid")
        if self.domain_z_spacing <= 0:
            raise ValueError("gui.domain_z_spacing must be > 0")
        if self.excitation_gamma <= 0:
            raise ValueError("gui.excitation_gamma must be > 0")
        if self.propagation_duration_seconds <= 0:
            raise ValueError("gui.propagation_duration_seconds must be > 0")
        if self.hover_pick_hz < 1:
            raise ValueError("gui.hover_pick_hz must be >= 1")
        if self.focus_line_width <= 0:
            raise ValueError("gui.focus_line_width must be > 0")
        if self.focus_node_scale < 1 or self.focus_neighbor_scale < 1:
            raise ValueError("gui focus node scales must be >= 1")
        if self.edge_pick_radius_px <= 0:
            raise ValueError("gui.edge_pick_radius_px must be > 0")
        if self.propagation_cycles_per_second <= 0:
            raise ValueError("gui.propagation_cycles_per_second must be > 0")
        if self.propagation_tail_points < 2:
            raise ValueError("gui.propagation_tail_points must be >= 2")
        if not 0 < self.propagation_tail_spacing < 1:
            raise ValueError("gui.propagation_tail_spacing must be in (0, 1)")
        if self.propagation_edge_width <= 0:
            raise ValueError("gui.propagation_edge_width must be > 0")


@dataclass(frozen=True, slots=True)
class OrchestratorSettings:
    # Three synchronous causal hops are the minimum needed for a resolved lexical
    # mention to reach its proposition: S -> T -> N. These are turn-local settling
    # ticks and suppress *new* pacemaker pulses; the scheduled clock remains 1 Hz.
    ticks_after_input: int = 3
    ticks_after_response: int = 1
    auto_materialize_inference: bool = True
    parse_agent_response_to_h: bool = False

    def __post_init__(self) -> None:
        if self.ticks_after_input < 1:
            raise ValueError("orchestrator.ticks_after_input must be >= 1")
        if self.ticks_after_response < 0:
            raise ValueError("orchestrator.ticks_after_response must be >= 0")


@dataclass(frozen=True, slots=True)
class AppConfig:
    source_path: Path
    paths: PathsConfig
    llm: LLMConfig = field(default_factory=LLMConfig)
    integration: IntegrationSettings = field(default_factory=IntegrationSettings)
    ignition: IgnitionSettings = field(default_factory=IgnitionSettings)
    workspace: WorkspaceSettings = field(default_factory=WorkspaceSettings)
    lifecycle: LifecycleSettings = field(default_factory=LifecycleSettings)
    inference: InferenceSettings = field(default_factory=InferenceSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    persistence: PersistenceSettings = field(default_factory=PersistenceSettings)
    identity: IdentitySettings = field(default_factory=IdentitySettings)
    gui: GUISettings = field(default_factory=GUISettings)
    orchestrator: OrchestratorSettings = field(default_factory=OrchestratorSettings)


def load_config(path: str | Path) -> AppConfig:
    source = Path(path).expanduser().resolve()
    with source.open("rb") as fh:
        data = tomllib.load(fh)
    base = source.parent

    p = _section(data, "paths")
    project_dir = _path(base, p.get("project_dir", "..")) or base
    data_dir = _path(base, p.get("data_dir", "../data")) or (base / "../data").resolve()
    persistence_file = _path(base, p.get("persistence_file", "../data/ah_memory.json")) or (data_dir / "ah_memory.json")
    paths = PathsConfig(
        project_dir=project_dir,
        llm_model_dir=_path(base, p.get("llm_model_dir")),
        tokenizer_dir=_path(base, p.get("tokenizer_dir")),
        adapter_dir=_path(base, p.get("adapter_dir")),
        system_prompt_path=_path(base, p.get("system_prompt_path")),
        agent_prompt_path=_path(base, p.get("agent_prompt_path", p.get("system_prompt_path", "../prompts/agent.txt"))),
        perception_prompt_path=_path(base, p.get("perception_prompt_path", "../prompts/perception.txt")),
        perception_prompt_dir=_path(base, p.get("perception_prompt_dir", "../prompts/perception")),
        data_dir=data_dir,
        persistence_file=persistence_file,
        logs_dir=_path(base, p.get("logs_dir", "../logs")) or (base / "../logs").resolve(),
    )

    llm_raw = _section(data, "llm")
    llm_perception_raw = _section(llm_raw, "perception") if "perception" in llm_raw else {}
    llm_agent_raw = _section(llm_raw, "agent") if "agent" in llm_raw else {}
    llm = LLMConfig(
        enabled=bool(llm_raw.get("enabled", True)),
        backend=str(llm_raw.get("backend", "builtin_process")),
        ollama_base_url=str(llm_raw.get("ollama_base_url", "http://127.0.0.1:11434")),
        ollama_model=str(llm_raw.get("ollama_model", "")),
        loader_type=str(llm_raw.get("loader_type", "auto")),
        device_map=str(llm_raw.get("device_map", "auto")),
        dtype=str(llm_raw.get("dtype", "auto")),
        local_files_only=bool(llm_raw.get("local_files_only", True)),
        trust_remote_code=bool(llm_raw.get("trust_remote_code", True)),
        use_4bit=bool(llm_raw.get("use_4bit", False)),
        ctx_total=int(llm_raw.get("ctx_total", 0)),
        max_new_tokens=int(llm_raw.get("max_new_tokens", 256)),
        temperature=float(llm_raw.get("temperature", 0.2)),
        top_p=float(llm_raw.get("top_p", 0.9)),
        top_k=int(llm_raw.get("top_k", 40)),
        repetition_penalty=float(llm_raw.get("repetition_penalty", 1.05)),
        no_repeat_ngram_size=int(llm_raw.get("no_repeat_ngram_size", 0)),
        enable_thinking=bool(llm_raw.get("enable_thinking", False)),
        strip_thinking=bool(llm_raw.get("strip_thinking", True)),
        startup_timeout_seconds=float(llm_raw.get("startup_timeout_seconds", 180.0)),
        request_timeout_seconds=float(llm_raw.get("request_timeout_seconds", 240.0)),
        engine_script=_path(base, llm_raw.get("engine_script")),
        history_messages=int(llm_raw.get("history_messages", 0)),
        perception_protocol=str(llm_perception_raw.get("protocol", "adaptive_v3")),
        perception_probe_retry_attempts=int(llm_perception_raw.get("probe_retry_attempts", llm_perception_raw.get("repair_attempts", 1))),
        perception_ground_actants=bool(llm_perception_raw.get("ground_actants", True)),
        perception_max_acts=int(llm_perception_raw.get("max_acts", 4)),
        perception_max_actants_per_act=int(llm_perception_raw.get("max_actants_per_act", 8)),
        perception_predicate_symbol_language=str(llm_perception_raw.get("predicate_symbol_language", "en")),
        perception_morphology_backend=str(llm_perception_raw.get("morphology_backend", "auto")),
        perception=LLMRoleSettings(
            max_new_tokens=int(llm_perception_raw.get("max_new_tokens", 96)),
            temperature=float(llm_perception_raw.get("temperature", 0.0)),
            top_p=float(llm_perception_raw.get("top_p", 1.0)),
            top_k=int(llm_perception_raw.get("top_k", 0)),
            repetition_penalty=float(llm_perception_raw.get("repetition_penalty", 1.0)),
            no_repeat_ngram_size=int(llm_perception_raw.get("no_repeat_ngram_size", 0)),
            use_cache=bool(llm_perception_raw.get("use_cache", False)),
        ),
        agent_repair_attempts=int(llm_agent_raw.get("repair_attempts", 1)),
        agent_sanitize_context_echo=bool(llm_agent_raw.get("sanitize_context_echo", True)),
        agent=LLMRoleSettings(
            max_new_tokens=int(llm_agent_raw.get("max_new_tokens", 384)),
            temperature=float(llm_agent_raw.get("temperature", 0.2)),
            top_p=float(llm_agent_raw.get("top_p", 0.9)),
            top_k=int(llm_agent_raw.get("top_k", 40)),
            repetition_penalty=float(llm_agent_raw.get("repetition_penalty", 1.05)),
            no_repeat_ngram_size=int(llm_agent_raw.get("no_repeat_ngram_size", 0)),
            use_cache=bool(llm_agent_raw.get("use_cache", True)),
        ),
    )

    ir = _section(data, "integration")
    integration = IntegrationSettings(
        initial_hypernode_weight=float(ir.get("initial_hypernode_weight", 0.4)),
        experience_hypernode_weight=float(ir.get("experience_hypernode_weight", 0.3)),
        follow_link_weight=float(ir.get("follow_link_weight", 0.2)),
        cause_link_weight=float(ir.get("cause_link_weight", ir.get("follow_link_weight", 0.2))),
        initial_inferred_link_weight=float(ir.get("initial_inferred_link_weight", 0.25)),
    )

    ign = _section(data, "ignition")
    act = _section(ign, "activation") if "activation" in ign else {}
    dec = _section(ign, "decay") if "decay" in ign else {}
    pla = _section(ign, "plasticity") if "plasticity" in ign else {}
    seeds = _section(ign, "seeds") if "seeds" in ign else {}
    pace = _section(ign, "pacemaker") if "pacemaker" in ign else {}
    raw_domains = pace.get("domains", ["C", "P", "H"])
    if not isinstance(raw_domains, (list, tuple)):
        raise ValueError("ignition.pacemaker.domains must be an array")
    ignition = IgnitionSettings(
        tick_interval_seconds=float(ign.get("tick_interval_seconds", 1.0)),
        nu=float(ign.get("nu", 1.0)),
        x_max=float(ign.get("x_max", 1.0)),
        activation=ActivationSettings(
            kind=str(act.get("kind", "additive_clamp")),
            gain=float(act.get("gain", 1.0)),
            epsilon=float(act.get("epsilon", 1e-9)),
        ),
        decay=DecaySettings(
            kind=str(dec.get("kind", "sigmoid_epoch")),
            alpha=float(dec.get("alpha", 0.60)),
            midpoint_ticks=float(dec.get("midpoint_ticks", 12.0)),
            steepness=float(dec.get("steepness", 0.35)),
            half_life_ticks=float(dec.get("half_life_ticks", dec.get("midpoint_ticks", 12.0))),
            reactivation_reset_ratio=float(dec.get("reactivation_reset_ratio", 1.0)),
            reactivation_min_input=float(dec.get("reactivation_min_input", 0.05)),
        ),
        plasticity=PlasticitySettings(
            enabled=bool(pla.get("enabled", True)),
            link_kind=str(pla.get("link_kind", "additive_hebb")),
            hypernode_kind=str(pla.get("hypernode_kind", "additive_confirmation_refutation")),
            link_hebb_increment=float(pla.get("link_hebb_increment", 0.015)),
            link_async_decrement=float(pla.get("link_async_decrement", 0.002)),
            link_weight_floor=float(pla.get("link_weight_floor", 0.02)),
            ignore_pacemaker_only_events=bool(pla.get("ignore_pacemaker_only_events", True)),
            hypernode_confirmation_increment=float(pla.get("hypernode_confirmation_increment", 0.01)),
            hypernode_refutation_decrement=float(pla.get("hypernode_refutation_decrement", 0.15)),
        ),
        seeds=SeedSettings(
            new_fact=float(seeds.get("new_fact", 0.65)),
            reactivated_fact=float(seeds.get("reactivated_fact", 0.55)),
            experience=float(seeds.get("experience", 0.5)),
            sensory_symbol=float(seeds.get("sensory_symbol", 0.85)),
            resolved_symbol=float(seeds.get("resolved_symbol", 0.95)),
            query_recall=float(seeds.get("query_recall", 0.80)),
            correction=float(seeds.get("correction", 0.65)),
            pacemaker=float(seeds.get("pacemaker", 0.08)),
        ),
        pacemaker=PacemakerSettings(
            enabled=bool(pace.get("enabled", True)),
            target_policy=str(pace.get("target_policy", "round_robin")),
            include_symbols=bool(pace.get("include_symbols", True)),
            domains=tuple(str(x).upper() for x in raw_domains),
            random_seed=int(pace.get("random_seed", 0)),
        ),
    )

    wr = _section(data, "workspace")
    lifecycle_raw = _section(data, "lifecycle")
    inference_raw = _section(data, "inference")
    context_raw = _section(data, "context")
    persistence_raw = _section(data, "persistence")
    identity_raw = _section(data, "identity")
    gui_raw = _section(data, "gui")
    orchestrator_raw = _section(data, "orchestrator")

    config = AppConfig(
        source_path=source,
        paths=paths,
        llm=llm,
        integration=integration,
        ignition=ignition,
        workspace=WorkspaceSettings(threshold=float(wr.get("threshold", 0.35))),
        lifecycle=LifecycleSettings(
            initial_lifetime_ticks=int(lifecycle_raw.get("initial_lifetime_ticks", 200)),
            reinforced_lifetime_ticks=int(lifecycle_raw.get("reinforced_lifetime_ticks", 1000)),
            min_spacing_1_ticks=int(lifecycle_raw.get("min_spacing_1_ticks", 20)),
            min_spacing_2_ticks=int(lifecycle_raw.get("min_spacing_2_ticks", 50)),
            gc_enabled=bool(lifecycle_raw.get("gc_enabled", True)),
            orphan_cleanup=bool(lifecycle_raw.get("orphan_cleanup", True)),
        ),
        inference=InferenceSettings(
            max_depth=int(inference_raw.get("max_depth", 6)),
            max_expanded_states=int(inference_raw.get("max_expanded_states", 5000)),
        ),
        context=ContextSettings(
            max_tokens=int(context_raw.get("max_tokens", 8192)),
            include_structural_uids=bool(context_raw.get("include_structural_uids", True)),
            include_mt=bool(context_raw.get("include_mt", False)),
            max_dependency_depth=int(context_raw.get("max_dependency_depth", 8)),
            overflow_policy=str(context_raw.get("overflow_policy", "error")),
        ),
        persistence=PersistenceSettings(
            enabled=bool(persistence_raw.get("enabled", True)),
            load_on_start=bool(persistence_raw.get("load_on_start", True)),
            autosave_every_ticks=int(persistence_raw.get("autosave_every_ticks", 200)),
            save_runtime_state=bool(persistence_raw.get("save_runtime_state", True)),
            save_pending_impulses=bool(persistence_raw.get("save_pending_impulses", True)),
        ),
        identity=IdentitySettings(
            agent_name=str(identity_raw.get("agent_name", "АГент")),
            user_name=str(identity_raw.get("user_name", "Пользователь")),
        ),
        gui=GUISettings(
            refresh_hz=int(gui_raw.get("refresh_hz", 30)),
            render_mode=str(gui_raw.get("render_mode", "2.5d")),
            show_labels=bool(gui_raw.get("show_labels", True)),
            max_labels=int(gui_raw.get("max_labels", 120)),
            node_size_min=float(gui_raw.get("node_size_min", 7.0)),
            node_size_max=float(gui_raw.get("node_size_max", 24.0)),
            domain_z_spacing=float(gui_raw.get("domain_z_spacing", 5.0)),
            excitation_gamma=float(gui_raw.get("excitation_gamma", 0.7)),
            propagation_duration_seconds=float(gui_raw.get("propagation_duration_seconds", 0.9)),
            show_structural_edges=bool(gui_raw.get("show_structural_edges", True)),
            show_relation_edges=bool(gui_raw.get("show_relation_edges", True)),
            hover_enabled=bool(gui_raw.get("hover_enabled", True)),
            hover_pick_hz=int(gui_raw.get("hover_pick_hz", 30)),
            focus_line_width=float(gui_raw.get("focus_line_width", 3.0)),
            focus_node_scale=float(gui_raw.get("focus_node_scale", 1.35)),
            focus_neighbor_scale=float(gui_raw.get("focus_neighbor_scale", 1.18)),
            edge_pick_radius_px=float(gui_raw.get("edge_pick_radius_px", 8.0)),
            propagation_cycles_per_second=float(gui_raw.get("propagation_cycles_per_second", 1.25)),
            propagation_tail_points=int(gui_raw.get("propagation_tail_points", 4)),
            propagation_tail_spacing=float(gui_raw.get("propagation_tail_spacing", 0.055)),
            propagation_edge_width=float(gui_raw.get("propagation_edge_width", 2.4)),
        ),
        orchestrator=OrchestratorSettings(
            ticks_after_input=int(orchestrator_raw.get("ticks_after_input", 3)),
            ticks_after_response=int(orchestrator_raw.get("ticks_after_response", 1)),
            auto_materialize_inference=bool(orchestrator_raw.get("auto_materialize_inference", True)),
            parse_agent_response_to_h=bool(orchestrator_raw.get("parse_agent_response_to_h", False)),
        ),
    )
    return config


def validate_app_config(config: AppConfig) -> None:
    if not config.llm.enabled:
        return
    backend = config.llm.backend.strip().lower()
    if backend == "builtin_process" and config.paths.llm_model_dir is None:
        raise ValueError("paths.llm_model_dir is required when llm.backend=builtin_process")
    if backend == "ollama" and not config.llm.ollama_model.strip():
        raise ValueError("llm.ollama_model is required when llm.backend=ollama")
