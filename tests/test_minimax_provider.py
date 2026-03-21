"""Tests for MiniMax provider implementation."""

import os
from unittest.mock import patch

import pytest

from providers.shared import ProviderType
from providers.shared.temperature import RangeTemperatureConstraint
from providers.minimax import MiniMaxModelProvider


class TestMiniMaxProvider:
    """Test MiniMax provider functionality."""

    def setup_method(self):
        """Reset restriction state before each test."""

        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    def teardown_method(self):
        """Reset restriction state after each test."""

        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"})
    def test_initialization(self):
        """Provider should initialize with the documented global endpoint."""

        provider = MiniMaxModelProvider("test-key")
        assert provider.api_key == "test-key"
        assert provider.get_provider_type() == ProviderType.MINIMAX
        assert provider.base_url == "https://api.minimax.io/v1"

    @patch.dict(os.environ, {"MINIMAX_BASE_URL": "https://api.minimaxi.com/v1"}, clear=True)
    def test_initialization_with_env_base_url_override(self):
        """Provider should honor an explicit MiniMax base URL override."""

        provider = MiniMaxModelProvider("test-key")
        assert provider.base_url == "https://api.minimaxi.com/v1"

    def test_model_validation(self):
        """Registry-backed aliases should validate correctly."""

        provider = MiniMaxModelProvider("test-key")

        assert provider.validate_model_name("MiniMax-M2.7") is True
        assert provider.validate_model_name("minimax") is True
        assert provider.validate_model_name("m2.7") is True
        assert provider.validate_model_name("m2.7-fast") is True
        assert provider.validate_model_name("MiniMax-M2") is True

        assert provider.validate_model_name("MiniMax-M2.9") is False
        assert provider.validate_model_name("grok-4") is False

    def test_resolve_model_name(self):
        """Aliases should resolve to the canonical MiniMax IDs."""

        provider = MiniMaxModelProvider("test-key")

        assert provider._resolve_model_name("minimax") == "MiniMax-M2.7"
        assert provider._resolve_model_name("m2.7-fast") == "MiniMax-M2.7-highspeed"
        assert provider._resolve_model_name("m2.5") == "MiniMax-M2.5"
        assert provider._resolve_model_name("m2") == "MiniMax-M2"

    def test_get_capabilities_primary_model(self):
        """Primary coding model metadata should match the curated manifest."""

        provider = MiniMaxModelProvider("test-key")
        capabilities = provider.get_capabilities("minimax")

        assert capabilities.model_name == "MiniMax-M2.7"
        assert capabilities.friendly_name == "MiniMax (MiniMax-M2.7)"
        assert capabilities.context_window == 204_800
        assert capabilities.provider == ProviderType.MINIMAX
        assert capabilities.supports_extended_thinking is True
        assert capabilities.supports_function_calling is True
        assert capabilities.supports_json_mode is False
        assert capabilities.supports_images is False
        assert capabilities.supports_temperature is True
        assert isinstance(capabilities.temperature_constraint, RangeTemperatureConstraint)
        assert capabilities.temperature_constraint.min_temp == 0.0
        assert capabilities.temperature_constraint.max_temp == 1.0
        assert capabilities.temperature_constraint.default_temp == 1.0

    def test_unsupported_model_capabilities(self):
        """Unsupported models should raise a provider-specific error."""

        provider = MiniMaxModelProvider("test-key")

        with pytest.raises(ValueError, match="Unsupported model 'MiniMax-M2.9' for provider minimax"):
            provider.get_capabilities("MiniMax-M2.9")

    @patch.dict(os.environ, {"MINIMAX_ALLOWED_MODELS": "MiniMax-M2.7"})
    def test_model_restrictions(self):
        """Restrictions should apply to MiniMax models and aliases."""

        import utils.model_restrictions
        from providers.registry import ModelProviderRegistry

        utils.model_restrictions._restriction_service = None
        ModelProviderRegistry.reset_for_testing()

        provider = MiniMaxModelProvider("test-key")

        assert provider.validate_model_name("MiniMax-M2.7") is True
        assert provider.validate_model_name("minimax") is True
        assert provider.validate_model_name("MiniMax-M2.7-highspeed") is False

    def test_preferred_model_selection(self):
        """Provider preferences should favor MiniMax's coding-optimized SKUs."""

        from tools.models import ToolModelCategory

        provider = MiniMaxModelProvider("test-key")
        allowed_models = [
            "MiniMax-M2",
            "MiniMax-M2.1",
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
        ]

        assert provider.get_preferred_model(ToolModelCategory.EXTENDED_REASONING, allowed_models) == "MiniMax-M2.7"
        assert provider.get_preferred_model(ToolModelCategory.FAST_RESPONSE, allowed_models) == "MiniMax-M2.7-highspeed"
        assert provider.get_preferred_model(ToolModelCategory.BALANCED, allowed_models) == "MiniMax-M2.7"
