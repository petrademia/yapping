from collections import Counter, defaultdict


class TabularPolicyValue:
    """Small reproducible baseline for oracle-labelled state rows."""

    def __init__(self):
        self.actions = defaultdict(Counter)
        self.values = defaultdict(list)

    def fit(self, rows):
        for row in rows:
            self.actions[row["state_key"]][row["oracle_action"]] += 1
            self.values[row["state_key"]].append(float(row["oracle_value"]))
        return self

    def predict_action(self, row):
        counts = self.actions.get(row["state_key"])
        return (counts.most_common(1)[0][0] if counts
                else (row["legal_actions"][0] if row["legal_actions"] else None))

    def predict_value(self, row):
        values = self.values.get(row["state_key"])
        return sum(values) / len(values) if values else 0.0
