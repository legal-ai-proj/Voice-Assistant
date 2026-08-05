"""
Shared Pydantic validators. Currently just one, but real enough to earn
its own module: models sometimes send an empty string ("") for an
optional field instead of omitting it entirely, which fails UUID
validation with a confusing error. A real call crashed exactly this way
-- caller said "any barber is fine," the model sent `staff_id: ""`
instead of leaving it out, and the tool call errored twice in a row
with no recovery.

This is defensive hardening, not a substitute for correct prompting --
the prompt should still instruct the model to omit optional fields
entirely. But relying on prompt-following alone for something this
easy to guard against in code is fragile; models don't follow
instructions with 100% consistency, and a crashed tool call mid-call is
expensive (the caller notices, unlike a silently-corrected value).
"""

from typing import Any


def empty_str_to_none(value: Any) -> Any:
    """Use as a `mode="before"` validator on any `int | None` field."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value
