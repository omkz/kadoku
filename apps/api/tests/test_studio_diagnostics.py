"""The Studio diagnostics isolate provider reachability from tool support."""
import asyncio
from types import SimpleNamespace

from app.studio_diagnostics import _exception_types, _probe


def test_error_signature_omits_messages_and_sensitive_values(capsys):
    secret="never-print-this-key"
    try:
        try:
            raise ValueError(secret)
        except ValueError as err:
            raise ConnectionError("also-secret") from err
    except ConnectionError as err:
        signature=_exception_types(err)
    assert signature=="ConnectionError -> ValueError"
    assert secret not in signature
    assert "also-secret" not in signature


def test_text_and_tool_probe_success_and_failure_are_private(capsys):
    async def success(**kwargs):
        assert "api_key" in kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])

    async def failure(**kwargs):
        class APIConnectionError(Exception):
            status_code=500
        raise APIConnectionError("secret-example-provider-error")

    common={"api_key":"hidden-key","messages":[{"role":"user","content":"OK"}]}
    assert asyncio.run(_probe("Plain text",common,success)) is True
    assert asyncio.run(_probe("Minimal tools",common,failure)) is False
    output=capsys.readouterr().out
    assert "Plain text: OK" in output
    assert "APIConnectionError" in output
    assert "status=500" in output
    assert "hidden-key" not in output
    assert "secret-example-provider-error" not in output
