"""
One way of rounding a figure for display, shared by every place that words a percentage.

Python's round() rounds halves to the EVEN number (round(92.5) == 92, and f"{92.5:.0f}" is "92"), while the screen
(JavaScript Math.round) rounds halves UP (93). A confidence of exactly 92.5% therefore read 92% in the PDF and 93% on
the screen for the same line. Everything that words a percentage on the server goes through here so the screen, the
PDF and the explanations agree.
"""
import math


def round_half_up(value):
    """The nearest whole number, with exact halves rounded up (like JavaScript's Math.round for positive values)."""
    return int(math.floor(float(value) + 0.5))


def percent(fraction):
    """A 0..1 fraction as a whole-number percent, e.g. 0.925 -> 93."""
    return round_half_up(float(fraction) * 100)
