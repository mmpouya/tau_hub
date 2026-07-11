"""Typed value objects returned by the registry."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """A reusable prompt/skill definition stored in the hub.

    Skills follow the same idea as Tau's user skills: a named block of
    instructions (and optional config) that can be attached to agents to
    extend their behaviour without editing the base system prompt.

    Attributes
    ----------
    name:
        Unique skill name (the lookup key).
    description:
        Short human-readable summary of what the skill does.
    content:
        The skill body — instructions injected into the system prompt.
    config:
        Optional structured configuration for the consuming application.
    """

    name: str
    description: str = ""
    content: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    def as_prompt_section(self) -> str:
        """Render this skill as a Markdown section for a system prompt.

        Returns
        -------
        str
            A ``## Skill: <name>`` section containing the description and
            skill content, ready to append to an agent's system prompt.
        """
        lines = [f"## Skill: {self.name}"]
        if self.description:
            lines.append(self.description)
        if self.content:
            lines.append("")
            lines.append(self.content)
        return "\n".join(lines).strip()
