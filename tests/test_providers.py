from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from troedel.listing import SCHEMA
from troedel.providers import Image, ProviderError, ProviderNotConfigured, ProviderUnavailable, build
from troedel.providers.anthropic_api import AnthropicProvider
from troedel.providers.base import checked, parse_object, strict, violations
from troedel.providers.claude_cli import SWITCHES, ClaudeCliProvider
from troedel.providers.openai_compat import OpenAICompatProvider

from .conftest import DRAFT

PHOTO = Image("image/jpeg", b"\xff\xd8\xff fake")


class TestSchema:
    def test_strict_closes_objects_and_drops_limits(self) -> None:
        s = strict(SCHEMA)
        assert s["additionalProperties"] is False
        assert "minimum" not in s["properties"]["price"]
        assert "minimum" in SCHEMA["properties"]["price"], "the original must stay untouched"

    def test_a_good_answer_passes(self) -> None:
        assert violations(DRAFT, SCHEMA) == []

    @pytest.mark.parametrize(
        "change, expected",
        [
            ({"condition": "mint"}, "not one of"),
            ({"price": -5}, "below"),
            ({"price": "15"}, "expected integer"),
            ({"price": True}, "expected integer"),
            ({"facts": ["ok", 3]}, "facts[1]"),
        ],
    )
    def test_violations(self, change: dict[str, Any], expected: str) -> None:
        assert expected in " ".join(violations({**DRAFT, **change}, SCHEMA))

    def test_missing_field(self) -> None:
        answer = {k: v for k, v in DRAFT.items() if k != "title"}
        with pytest.raises(ProviderError, match="missing 'title'"):
            checked(answer, SCHEMA)

    @pytest.mark.parametrize(
        "text",
        [
            '{"a": 1}',
            '```json\n{"a": 1}\n```',
            'Here you go:\n{"a": 1}\nHope that helps.',
        ],
    )
    def test_parse_object_is_tolerant(self, text: str) -> None:
        assert parse_object(text) == {"a": 1}

    @pytest.mark.parametrize("text", ["no json here", "[1, 2]", "{broken"])
    def test_parse_object_rejects(self, text: str) -> None:
        with pytest.raises(ProviderError):
            parse_object(text)


def _response(data: dict[str, Any], stop: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop,
        model="claude-opus-5-5",
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(data))],
    )


class FakeAnthropic:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[dict[str, Any]] = []
        endpoint = SimpleNamespace(create=self._create)
        self.messages = endpoint
        self.beta = SimpleNamespace(messages=endpoint)

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _status_error(cls: type, status: int) -> Exception:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


class TestAnthropic:
    def test_request_shape(self) -> None:
        client = FakeAnthropic(_response(DRAFT))
        answer = AnthropicProvider("", client=client).ask("p", system="s", schema=SCHEMA, images=[PHOTO])
        assert answer.data == DRAFT and answer.model == "claude-opus-5-5"
        request = client.requests[0]
        assert request["model"] == "claude-opus-5-5" and request["system"] == "s"
        image, text = request["messages"][0]["content"]
        assert image["source"]["media_type"] == "image/jpeg" and text == {"type": "text", "text": "p"}
        fmt = request["output_config"]["format"]
        assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
        assert request["fallbacks"] == "default" and request["betas"]
        # Removed parameters on current models: sending them is a 400.
        assert "tool_choice" not in request and "thinking" not in request and "temperature" not in request

    def test_haiku_gets_no_effort_and_no_fallbacks(self) -> None:
        client = FakeAnthropic(_response(DRAFT))
        AnthropicProvider("", client=client).ask("p", system="s", schema=SCHEMA, images=[], model="claude-haiku-4-5")
        request = client.requests[0]
        assert "effort" not in request["output_config"] and "fallbacks" not in request

    def test_refusal_is_not_read_as_an_answer(self) -> None:
        client = FakeAnthropic(_response({}, stop="refusal"))
        with pytest.raises(ProviderError) as exc:
            AnthropicProvider("", client=client).ask("p", system="s", schema=SCHEMA, images=[])
        assert exc.value.code == "declined"

    @pytest.mark.parametrize(
        "error, kind, code",
        [
            (_status_error(anthropic.RateLimitError, 429), ProviderUnavailable, "unavailable"),
            (_status_error(anthropic.InternalServerError, 529), ProviderUnavailable, "unavailable"),
            (_status_error(anthropic.AuthenticationError, 401), ProviderError, "auth"),
            (_status_error(anthropic.NotFoundError, 404), ProviderError, "model"),
            (_status_error(anthropic.BadRequestError, 400), ProviderError, "failed"),
        ],
    )
    def test_errors(self, error: Exception, kind: type, code: str) -> None:
        with pytest.raises(kind) as exc:
            AnthropicProvider("", client=FakeAnthropic(error)).ask("p", system="s", schema=SCHEMA, images=[])
        assert exc.value.code == code

    def test_needs_a_key(self) -> None:
        with pytest.raises(ProviderNotConfigured):
            AnthropicProvider("")


def _openai(handler: Any, name: str = "gemini", key: str = "k", **kw: Any) -> OpenAICompatProvider:
    return OpenAICompatProvider(name, key, client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def _reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


class TestOpenAICompat:
    def test_request_shape(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _reply(json.dumps(DRAFT))

        answer = _openai(handler).ask("p", system="s", schema=SCHEMA, images=[PHOTO])
        assert answer.data == DRAFT
        request = seen[0]
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert request.headers["authorization"] == "Bearer k"
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.6-flash" and "JSON Schema" in body["messages"][0]["content"]
        assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_one_retry_with_the_complaint(self) -> None:
        replies = [json.dumps({**DRAFT, "condition": "mint"}), json.dumps(DRAFT)]
        bodies: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return _reply(replies.pop(0))

        assert _openai(handler).ask("p", system="s", schema=SCHEMA, images=[]).data == DRAFT
        assert "not one of" in bodies[1]["messages"][-1]["content"]

    def test_gives_up_after_the_retry(self) -> None:
        with pytest.raises(ProviderError) as exc:
            _openai(lambda r: _reply("sorry, no")).ask("p", system="s", schema=SCHEMA, images=[])
        assert exc.value.code == "invalid"

    @pytest.mark.parametrize(
        "status, kind, code",
        [
            (429, ProviderUnavailable, "unavailable"),
            (503, ProviderUnavailable, "unavailable"),
            (401, ProviderError, "auth"),
            (404, ProviderError, "model"),
            (400, ProviderError, "failed"),
        ],
    )
    def test_errors(self, status: int, kind: type, code: str) -> None:
        with pytest.raises(kind) as exc:
            _openai(lambda r: httpx.Response(status, text="nope")).ask("p", system="s", schema=SCHEMA, images=[])
        assert exc.value.code == code

    def test_a_bad_key_answered_with_400_is_still_a_key_problem(self) -> None:
        reply = httpx.Response(400, json=[{"error": {"code": 400, "message": "Please pass a valid API key"}}])
        with pytest.raises(ProviderError) as exc:
            _openai(lambda r: reply).ask("p", system="s", schema=SCHEMA, images=[])
        assert exc.value.code == "auth"

    def test_network_failure_is_worth_retrying_later(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        with pytest.raises(ProviderUnavailable):
            _openai(handler).ask("p", system="s", schema=SCHEMA, images=[])

    def test_what_must_be_configured(self) -> None:
        with pytest.raises(ProviderNotConfigured, match="API key"):
            OpenAICompatProvider("gemini", "")
        with pytest.raises(ProviderNotConfigured, match="model"):
            OpenAICompatProvider("openai", "k")
        with pytest.raises(ProviderNotConfigured, match="base URL"):
            OpenAICompatProvider("custom", "", model="m")
        local = OpenAICompatProvider("ollama", "", model="some-vision-model")
        assert local.base_url.startswith("http://127.0.0.1")


class TestClaudeCli:
    def test_the_model_gets_no_tools(self) -> None:
        """The boundary of this provider. Loosening it lets a prompt hidden
        in a photo act on the machine."""
        i = SWITCHES.index("--tools")
        assert SWITCHES[i + 1] == ""
        for switch in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
            assert switch in SWITCHES
        assert SWITCHES[SWITCHES.index("--setting-sources") + 1] == ""
        for forbidden in ("--dangerously-skip-permissions", "--add-dir", "--allowedTools"):
            assert forbidden not in SWITCHES

    def test_photos_travel_as_content_blocks(self) -> None:
        message = json.loads(ClaudeCliProvider.message("p", [PHOTO]))
        image, text = message["message"]["content"]
        assert image["type"] == "image" and text == {"type": "text", "text": "p"}

    def test_reads_the_result_line(self) -> None:
        out = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "result": "x",
                        "structured_output": DRAFT,
                        "modelUsage": {"claude-opus-5-5": {}},
                    }
                ),
            ]
        )
        answer = ClaudeCliProvider.read(out, "", 0, SCHEMA, "opus")
        assert answer.data == DRAFT and answer.model == "claude-opus-5-5"

    def test_limit_is_worth_retrying_later(self) -> None:
        out = json.dumps({"type": "result", "subtype": "error", "is_error": True, "result": "Usage limit reached"})
        with pytest.raises(ProviderUnavailable):
            ClaudeCliProvider.read(out, "", 1, SCHEMA, "opus")

    def test_no_output(self) -> None:
        with pytest.raises(ProviderError):
            ClaudeCliProvider.read("", "command failed", 1, SCHEMA, "opus")

    def test_missing_binary(self) -> None:
        with pytest.raises(ProviderNotConfigured):
            ClaudeCliProvider(binary="definitely-not-installed-anywhere")

    @pytest.mark.skipif(sys.platform == "win32", reason="needs an executable script")
    def test_found_without_the_path_of_a_terminal(self, tmp_path, monkeypatch) -> None:
        """Started from the Finder, Trödel gets a PATH without the folders
        the program is installed in."""
        program = tmp_path / ".local" / "bin" / "claude"
        program.parent.mkdir(parents=True)
        program.write_text("#!/bin/sh\n")
        program.chmod(0o755)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        provider = ClaudeCliProvider()
        assert provider.binary == str(program)
        assert provider.path.split(os.pathsep)[:2] == ["/usr/bin", "/bin"]
        assert str(program.parent) in provider.path.split(os.pathsep)


def test_build_says_what_is_missing() -> None:
    with pytest.raises(ProviderNotConfigured):
        build("")
    with pytest.raises(ProviderNotConfigured):
        build("teapot")
    assert build("gemini", api_key="k").name == "gemini"
