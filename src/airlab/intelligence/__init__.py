"""Provider-neutral AIrLab Intelligence Gateway."""

from .composition import create_environment_gateway
from .gateway import (
    GatewayUnavailable,
    IntelligenceGateway,
    ProviderExecutionError,
    create_control_gateway,
)
from .openai_compatible import (
    HttpxJsonTransport,
    JsonHttpResponse,
    OpenAICompatibleProbe,
    OpenAICompatibleProvider,
)
from .registry import CapabilityRegistry, ProviderRegistry, default_capability_registry
from .router import IntelligenceRouter, RoutingError

__all__ = [
    "CapabilityRegistry",
    "GatewayUnavailable",
    "IntelligenceGateway",
    "HttpxJsonTransport",
    "IntelligenceRouter",
    "JsonHttpResponse",
    "OpenAICompatibleProbe",
    "OpenAICompatibleProvider",
    "ProviderExecutionError",
    "ProviderRegistry",
    "RoutingError",
    "create_control_gateway",
    "create_environment_gateway",
    "default_capability_registry",
]
