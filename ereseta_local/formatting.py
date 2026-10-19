"""Shared display formatting for prescription quantities."""


def format_quantity(value) -> str:
    """Keep exactly one quantity prefix, including for an empty quantity."""
    return "#" + ("" if value is None else str(value)).lstrip("# \t\r\n").rstrip()
