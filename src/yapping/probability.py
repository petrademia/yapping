from math import comb


def opening_probability(deck_size, copies, hand_size):
    """Probability of opening at least one of `copies` without replacement."""
    if not 0 <= copies <= deck_size or not 0 <= hand_size <= deck_size:
        raise ValueError("copies and hand_size must fit inside deck_size")
    return 1 - comb(deck_size - copies, hand_size) / comb(deck_size, hand_size)


def opening_count_probability(deck_size, copies, hand_size, count):
    """Hypergeometric P(exactly ``count`` successes in ``hand_size`` draws).

    ``copies`` is the success population (for example, cards with a given role).
    Overlapping roles across different labels are out of scope here: pass the
    success count for one role at a time.
    """
    if not 0 <= copies <= deck_size or not 0 <= hand_size <= deck_size:
        raise ValueError("copies and hand_size must fit inside deck_size")
    if count < 0 or count > hand_size or count > copies:
        return 0.0
    failures = deck_size - copies
    drawn_failures = hand_size - count
    if drawn_failures < 0 or drawn_failures > failures:
        return 0.0
    return comb(copies, count) * comb(failures, drawn_failures) / comb(deck_size, hand_size)


def opening_at_least_probability(deck_size, copies, hand_size, minimum):
    """Hypergeometric P(at least ``minimum`` successes in ``hand_size`` draws)."""
    if minimum <= 0:
        return 1.0
    if not 0 <= copies <= deck_size or not 0 <= hand_size <= deck_size:
        raise ValueError("copies and hand_size must fit inside deck_size")
    if minimum > hand_size or minimum > copies:
        return 0.0
    upper = min(hand_size, copies)
    return sum(
        opening_count_probability(deck_size, copies, hand_size, count)
        for count in range(minimum, upper + 1)
    )
