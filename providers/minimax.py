"""MiniMax model provider implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

from utils.env import get_env

from .openai_compatible import OpenAICompatibleProvider
from .registries.minimax import MiniMaxModelRegistry
from .registry_provider_mixin import RegistryBackedProviderMixin
from .shared import ModelCapabilities, ProviderType, RangeTemperatureConstraint

logger = logging.getLogger(__name__)


class MiniMaxModelProvider(RegistryBackedProviderMixin, OpenAICompatibleProvider):
    """Integration for MiniMax's direct OpenAI-compatible text API."""

    FRIENDLY_NAME = "MiniMax"

    REGISTRY_CLASS = MiniMaxModelRegistry
    MODEL_CAPABILITIES: ClassVar[dict[str, ModelCapabilities]] = {}
    _temperature_overrides_applied: ClassVar[bool] = False

    PRIMARY_MODEL = "MiniMax-M2.7"
    FAST_MODEL = "MiniMax-M2.7-highspeed"
    FALLBACK_MODEL = "MiniMax-M2.5"
    LEGACY_MODEL = "MiniMax-M2.1"

    @classmethod
    def _apply_provider_overrides(cls) -> None:
        """Apply provider-specific capability adjustments after registry load."""

        if cls._temperature_overrides_applied:
            return

        for capabilities in cls.MODEL_CAPABILITIES.values():
            capabilities.temperature_constraint = RangeTemperatureConstraint(0.0, 1.0, 1.0)
            capabilities.supports_temperature = True

        cls._temperature_overrides_applied = True

    @classmethod
    def _ensure_registry(cls, *, force_reload: bool = False) -> None:
        """Populate registry data and apply MiniMax-specific capability fixes."""

        super()._ensure_registry(force_reload=force_reload)
        if force_reload:
            cls._temperature_overrides_applied = False
        cls._apply_provider_overrides()

    def __init__(self, api_key: str, **kwargs):
        """Initialize MiniMax provider with API key and optional base URL override."""

        self._ensure_registry()
        kwargs.setdefault("base_url", get_env("MINIMAX_BASE_URL") or "https://api.minimax.io/v1")
        super().__init__(api_key, **kwargs)
        self._invalidate_capability_cache()

    def get_provider_type(self) -> ProviderType:
        """Return the provider type."""

        return ProviderType.MINIMAX

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """Get MiniMax's preferred model for a given category from allowed models."""

        from tools.models import ToolModelCategory

        if not allowed_models:
            return None

        def find_first(preferences: list[str]) -> Optional[str]:
            for model in preferences:
                if model in allowed_models:
                    return model
            return None

        if category == ToolModelCategory.EXTENDED_REASONING:
            preferred = find_first(
                [
                    self.PRIMARY_MODEL,
                    self.FALLBACK_MODEL,
                    self.FAST_MODEL,
                    self.LEGACY_MODEL,
                ]
            )
            return preferred if preferred else allowed_models[0]

        if category == ToolModelCategory.FAST_RESPONSE:
            preferred = find_first(
                [
                    self.FAST_MODEL,
                    self.PRIMARY_MODEL,
                    self.FALLBACK_MODEL,
                    self.LEGACY_MODEL,
                ]
            )
            return preferred if preferred else allowed_models[0]

        preferred = find_first(
            [
                self.PRIMARY_MODEL,
                self.FAST_MODEL,
                self.FALLBACK_MODEL,
                self.LEGACY_MODEL,
            ]
        )
        return preferred if preferred else allowed_models[0]


MiniMaxModelProvider._ensure_registry()
