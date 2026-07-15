"""Compare sampled determinization with exact hidden maximin."""

import argparse
import contextlib
import io
import json

from matchup_config import load_config
from search_hidden_ash import search as exact_search
from search_sampled_hidden import search as sampled_search
from trace_albaz_combo import card_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", default="ash")
    parser.add_argument("--hand", type=card_id, nargs=5)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--max-nodes", type=int, default=1000)
    parser.add_argument("--max-depth", type=int, default=80)
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    with contextlib.redirect_stdout(io.StringIO()):
        exact = exact_search(args.interruption, args.max_nodes, args.max_depth,
                             args.hand, config)
    sampled = sampled_search(args.interruption, args.hand, args.samples, 7,
                             args.max_nodes, args.max_depth, config)
    print(json.dumps({
        "comparison": "sampled_expected_value_vs_exact_worst_case",
        "exact": {"score": exact.score, "complete": exact.complete,
                  "guarantee": "worst_case_over_hidden_worlds"},
        "sampled": sampled,
        "bias_gap": (sampled["chosen"]["mean"] - exact.score
                      if sampled["chosen"] else None),
    }, indent=2, sort_keys=True))
