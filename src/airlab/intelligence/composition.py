from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from airlab.resources import (
    ResourcePoolStateManager,
    UsageLedger,
    free_resource_pool_v1,
)

from .contracts import AccessClass
from .gateway import DiagnosticsSink, IntelligenceGateway
from .openai_compatible import (
    JsonHttpTransport,
    OpenAICompatibleProbe,
    OpenAICompatibleProvider,
)
from .registry import ProviderRegistry, default_capability_registry
from .resource_pool import (
    ProviderBinding,
    ResourcePoolBridge,
    provider_descriptor_from_resource,
)


@dataclass(frozen=True)
class OpenAIProviderTemplate:
    resource_id: str
    secret_name: str
    endpoint: str
    model: str
    gateway_capabilities: frozenset[str]
    context_window: int
    access_class: AccessClass
    quality_score: float = 0.5


_OPENROUTER_FREE = OpenAIProviderTemplate(
    resource_id="openrouter_free_pool",
    secret_name="AIRLAB_OPENROUTER_API_KEY",
    endpoint="https://openrouter.ai/api/v1/chat/completions",
    model="openrouter/free",
    gateway_capabilities=frozenset(
        {
            "chat.general",
            "reasoning.fast",
            "reasoning.deep",
            "coding.generate",
            "coding.review",
            "coding.debug",
            "architecture",
            "summarize",
            "classify",
            "long_context",
            "research",
        }
    ),
    context_window=200_000,
    access_class="recurring_free",
    quality_score=0.5,
)


_NVIDIA_NIM = OpenAIProviderTemplate(
    resource_id="nvidia_nim_developer",
    secret_name="AIRLAB_NVIDIA_API_KEY",
    endpoint="https://integrate.api.nvidia.com/v1/chat/completions",
    model="nvidia/nemotron-3-ultra-550b-a55b",
    gateway_capabilities=frozenset(
        {
            "chat.general",
            "reasoning.fast",
            "reasoning.deep",
            "coding.generate",
            "coding.review",
            "coding.debug",
            "architecture",
            "summarize",
            "classify",
            "long_context",
            "research",
        }
    ),
    context_window=1_000_000,
    access_class="development_free",
    quality_score=0.5,
)

OPENAI_COMPATIBLE_TEMPLATES = (_OPENROUTER_FREE, _NVIDIA_NIM)


def create_environment_gateway(
    diagnostics: DiagnosticsSink,
    *,
    secrets: Mapping[str, str],
    transport: JsonHttpTransport | None = None,
    probe_configured: bool = True,
) -> IntelligenceGateway:
    """Compose real remote providers from secrets without changing public API.

    Missing credentials simply mean a provider is absent. Configured remote
    resources still start UNKNOWN and are schedulable only after an authenticated
    probe proves current availability.
    """

    capabilities = default_capability_registry()
    resources = free_resource_pool_v1()
    state_manager = ResourcePoolStateManager(registry=resources)
    bridge = ResourcePoolBridge(resources, state_manager=state_manager)
    providers = ProviderRegistry()
    adapters: list[OpenAICompatibleProvider] = []

    for template in OPENAI_COMPATIBLE_TEMPLATES:
        credential = str(secrets.get(template.secret_name, "") or "").strip()
        if not credential:
            continue

        resource = resources.get(template.resource_id)
        if resource is None:
            continue

        binding = ProviderBinding(
            resource_id=template.resource_id,
            endpoint=template.endpoint,
            model=template.model,
            gateway_capabilities=template.gateway_capabilities,
            context_window=template.context_window,
            quality_score=template.quality_score,
            access_class=template.access_class,
            adapter_id="openai_compatible",
        )
        descriptor = provider_descriptor_from_resource(resource, binding)
        providers.register(descriptor)

        adapter = OpenAICompatibleProvider(
            provider_id=template.resource_id,
            endpoint=template.endpoint,
            api_key_provider=lambda value=credential: value,
            transport=transport,
        )
        adapters.append(adapter)

        if probe_configured:
            state_manager.probe(
                OpenAICompatibleProbe(
                    resource_id=template.resource_id,
                    provider=adapter,
                    model=template.model,
                )
            )

    return IntelligenceGateway(
        capabilities=capabilities,
        providers=providers,
        adapters=adapters,
        diagnostics=diagnostics,
        resource_pool=bridge,
        usage_ledger=UsageLedger(),
    )
