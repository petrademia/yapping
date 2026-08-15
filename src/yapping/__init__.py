from .env import YgoEnv
from .minimax import HiddenMinimaxResult, MinimaxResult, hidden_minimax_replay, minimax_replay
from .probability import (
    opening_at_least_probability,
    opening_count_probability,
    opening_probability,
)
from .adversarial import RobustChoice, expected_choice, robust_choice
from .engine import Decision, Engine
from .search import SearchResult, search
from .archetype import Archetype, Fixture, Interruption, load_archetype
from .compendium import summarize_compendium
from .combo import load_combo
from .evaluation import EndboardEvaluator, EvaluationState
from .provenance import report_provenance
from .learning import ORACLE_SCHEMA_VERSION, action_descriptor, snapshot_observation, validate_example
from .roles import (
    cards_with_role,
    count_roles,
    hand_features,
    normalize_card_roles,
    role_copies_in_deck,
    roles_for,
)
from .consistency import (
    HandCondition,
    ceiling,
    conditional_bucket_deltas,
    conditioned_hand_utility,
    expected_utility,
    floor_over_configured,
    hand_feature_access_rates,
    interruption_loss,
    quantified_hand_report,
    role_density_opening_profile,
    summarize_by_predicate,
    summarize_joint_conditions,
    summarize_role_counts,
    summarize_rows,
    utility_distribution,
    weighted_quantile,
)
from .variants import DeckVariant, SlotCandidate

__all__ = [
    "Decision", "Engine", "HiddenMinimaxResult", "MinimaxResult", "RobustChoice", "SearchResult",
    "YgoEnv", "expected_choice", "hidden_minimax_replay", "minimax_replay", "opening_probability",
    "opening_count_probability", "opening_at_least_probability",
    "robust_choice", "search", "Archetype", "Fixture", "Interruption", "load_archetype",
    "summarize_compendium",
    "load_combo",
    "EndboardEvaluator", "EvaluationState",
    "report_provenance",
    "ORACLE_SCHEMA_VERSION", "action_descriptor", "snapshot_observation", "validate_example",
    "DeckVariant", "SlotCandidate",
    "normalize_card_roles", "roles_for", "cards_with_role", "count_roles",
    "hand_features", "role_copies_in_deck",
    "HandCondition", "conditioned_hand_utility", "summarize_rows", "summarize_by_predicate",
    "summarize_role_counts", "summarize_joint_conditions", "role_density_opening_profile",
    "utility_distribution", "weighted_quantile", "quantified_hand_report",
    "hand_feature_access_rates", "conditional_bucket_deltas",
    "ceiling", "interruption_loss", "floor_over_configured", "expected_utility",
]
