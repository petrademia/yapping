"""
Formats combos into JSON or Flowcharts.

Takes the output of the simulator (paths, end-boards, actions) and
exports to:
- JSON (machine-readable, for tools or replay)
- Flowcharts (human-readable diagrams of branches)
"""

# TODO: implement export(paths, format="json"|"flowchart") -> file or str
# - JSON: list of { path: [...], score, end_board }
# - Flowchart: e.g. Mermaid or similar from path tree
