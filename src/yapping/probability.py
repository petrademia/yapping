from math import comb


def opening_probability(deck_size, copies, hand_size):
    """Probability of opening at least one of `copies` without replacement."""
    if not 0 <= copies <= deck_size or not 0 <= hand_size <= deck_size:
        raise ValueError("copies and hand_size must fit inside deck_size")
    return 1 - comb(deck_size - copies, hand_size) / comb(deck_size, hand_size)
