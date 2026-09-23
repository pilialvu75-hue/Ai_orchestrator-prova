from __future__ import annotations

import unittest

from airlab.intelligence.composition import create_environment_gateway
from airlab.intelligence.contracts import (
    GatewayMessage,
    GatewayRequest,
    RoutePolicy,
)
from airlab.intelligence.gateway import GatewayUnavailable, ProviderExecutionError
from airlab.intelligence.openai_compatible import (
    JsonHttpResponse,
    OpenAICompatibleProbe,
    OpenAICompatibleProvider,
)
from airlab.resources import ResourceHealth


class Diagnostics:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, fields: dict[str, object]) -> None:
        self.events.append((event, fields))


class FakeTransport:
    def __init__(self, responses: list[JsonHttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post_json(
        self,
        url: str,
        *,
        headers,
        payload,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


def ok_response(
    text: str = "ok",
    *,
    model: str = "remote-model",
) -> JsonHttpResponse:
    return JsonHttpResponse(
        status_code=200,
        payload={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        },
        headers={},
    )


class OpenAICompatibleProviderTests(unittest.TestCase):
    def test_completion_translates_gateway_request_without_provider_in_prompt(self) -> None:
        transport = FakeTransport([ok_response("remote answer")])
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "secret-value",
            transport=transport,
        )
        request = GatewayRequest(
            capability="coding.review",
            messages=(
                GatewayMessage(role="system", content="be concise"),
                GatewayMessage(role="user", content="review this"),
            ),
            max_tokens=77,
            temperature=0.4,
        )

        output = provider.complete(request, model="model-a")

        self.assertEqual(output.text, "remote answer")
        self.assertEqual(output.model, "remote-model")
        self.assertEqual(output.usage["total_tokens"], 5)
        call = transport.calls[0]
        self.assertEqual(
            call["url"],
            "https://provider.example/v1/chat/completions",
        )
        self.assertEqual(
            call["headers"]["authorization"],
            "Bearer secret-value",
        )
        self.assertEqual(call["payload"]["model"], "model-a")
        self.assertEqual(call["payload"]["max_tokens"], 77)
        self.assertEqual(call["payload"]["temperature"], 0.4)
        self.assertEqual(
            call["payload"]["messages"],
            [
                {"role": "system", "content": "be concise"},
                {"role": "user", "content": "review this"},
            ],
        )
        self.assertNotIn("provider-a", repr(call["payload"]))

    def test_missing_credential_fails_before_network(self) -> None:
        transport = FakeTransport([])
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "",
            transport=transport,
        )

        with self.assertRaises(ProviderExecutionError) as raised:
            provider.complete(
                GatewayRequest(
                    capability="chat.general",
                    messages=(GatewayMessage(role="user", content="hello"),),
                ),
                model="model-a",
            )

        self.assertEqual(raised.exception.kind, "authentication")
        self.assertEqual(transport.calls, [])

    def test_rate_limit_and_retry_after_are_normalized(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=429,
                    payload={"error": {"message": "too many requests"}},
                    headers={"retry-after": "12"},
                )
            ]
        )
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "secret",
            transport=transport,
        )

        with self.assertRaises(ProviderExecutionError) as raised:
            provider.complete(
                GatewayRequest(
                    capability="chat.general",
                    messages=(GatewayMessage(role="user", content="hello"),),
                ),
                model="model-a",
            )

        self.assertEqual(raised.exception.kind, "rate_limit")
        self.assertEqual(raised.exception.retry_after_seconds, 12)

    def test_quota_error_is_distinct_from_rate_limit(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=429,
                    payload={"error": {"code": "insufficient_quota"}},
                    headers={},
                )
            ]
        )
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "secret",
            transport=transport,
        )

        with self.assertRaises(ProviderExecutionError) as raised:
            provider.complete(
                GatewayRequest(
                    capability="chat.general",
                    messages=(GatewayMessage(role="user", content="hello"),),
                ),
                model="model-a",
            )

        self.assertEqual(raised.exception.kind, "quota")
        self.assertTrue(raised.exception.retryable)

    def test_invalid_request_is_not_retried_as_provider_failure(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=400,
                    payload={"error": {"message": "bad request"}},
                    headers={},
                )
            ]
        )
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "secret",
            transport=transport,
        )

        with self.assertRaises(ProviderExecutionError) as raised:
            provider.complete(
                GatewayRequest(
                    capability="chat.general",
                    messages=(GatewayMessage(role="user", content="hello"),),
                ),
                model="model-a",
            )

        self.assertEqual(raised.exception.kind, "invalid_request")
        self.assertFalse(raised.exception.retryable)

    def test_probe_accepts_valid_choices_even_when_content_is_empty(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=200,
                    payload={"choices": [{"message": {"content": ""}}]},
                    headers={},
                )
            ]
        )
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "secret",
            transport=transport,
        )

        snapshot = OpenAICompatibleProbe(
            resource_id="provider-a",
            provider=provider,
            model="model-a",
        ).probe()

        self.assertEqual(snapshot.health, ResourceHealth.HEALTHY)
        self.assertEqual(snapshot.availability, "api_reachable")

    def test_probe_auth_failure_is_not_schedulable_health(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=401,
                    payload={"error": {"message": "invalid key"}},
                    headers={},
                )
            ]
        )
        provider = OpenAICompatibleProvider(
            provider_id="provider-a",
            endpoint="https://provider.example/v1/chat/completions",
            api_key_provider=lambda: "secret",
            transport=transport,
        )

        snapshot = OpenAICompatibleProbe(
            resource_id="provider-a",
            provider=provider,
            model="model-a",
        ).probe()

        self.assertEqual(snapshot.health, ResourceHealth.DOWN)
        self.assertEqual(snapshot.availability, "authentication_required")


class EnvironmentCompositionTests(unittest.TestCase):
    def test_no_provider_secret_means_no_remote_provider(self) -> None:
        diagnostics = Diagnostics()
        gateway = create_environment_gateway(
            diagnostics,
            secrets={},
            transport=FakeTransport([]),
        )

        self.assertEqual(gateway.providers_snapshot(), [])
        with self.assertRaises(GatewayUnavailable):
            gateway.complete(
                GatewayRequest(
                    capability="chat.general",
                    messages=(GatewayMessage(role="user", content="hello"),),
                )
            )

    def test_configured_nvidia_is_probed_then_used_through_generic_adapter(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=200,
                    payload={"choices": [{"message": {"content": ""}}]},
                    headers={},
                ),
                ok_response("nemotron answer", model="nvidia/served-model"),
            ]
        )
        diagnostics = Diagnostics()
        gateway = create_environment_gateway(
            diagnostics,
            secrets={"AIRLAB_NVIDIA_API_KEY": "nvidia-secret"},
            transport=transport,
        )

        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="design this"),),
            )
        )

        self.assertEqual(response.text, "nemotron answer")
        self.assertEqual(response.provider_id, "nvidia_nim_developer")
        self.assertEqual(response.model, "nvidia/served-model")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(
            transport.calls[0]["url"],
            "https://integrate.api.nvidia.com/v1/chat/completions",
        )
        self.assertEqual(
            transport.calls[1]["headers"]["authorization"],
            "Bearer nvidia-secret",
        )

    def test_nvidia_development_binding_cannot_serve_commercial_request(self) -> None:
        transport = FakeTransport(
            [
                JsonHttpResponse(
                    status_code=200,
                    payload={"choices": [{"message": {"content": ""}}]},
                    headers={},
                )
            ]
        )
        gateway = create_environment_gateway(
            Diagnostics(),
            secrets={"AIRLAB_NVIDIA_API_KEY": "nvidia-secret"},
            transport=transport,
        )

        with self.assertRaises(GatewayUnavailable):
            gateway.complete(
                GatewayRequest(
                    capability="architecture",
                    messages=(GatewayMessage(role="user", content="commercial"),),
                    policy=RoutePolicy(
                        environment="commercial",
                        free_only=True,
                        paid_allowed=False,
                    ),
                )
            )

        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
