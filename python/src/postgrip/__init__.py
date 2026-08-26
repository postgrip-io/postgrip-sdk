"""Unified PostGrip SDK with lazy root-facade imports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import AsyncPostGrip, PostGrip

__all__ = ["AsyncPostGrip", "PostGrip"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .client import AsyncPostGrip, PostGrip

        return {"AsyncPostGrip": AsyncPostGrip, "PostGrip": PostGrip}[name]
    raise AttributeError(name)
