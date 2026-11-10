"""The AG Studio agent proxy is authenticated, bounded, and forwards tool calls."""
from types import SimpleNamespace

from app.core.config import get_settings
from app.routers import studio_agent as agent


ENDPOINT = "/api/v1/admin/analytics/agent"


def headers(token_factory, subject="test-user-a"):
    return {"Authorization": "Bearer " + token_factory(sub=subject)}


def payload(**changes):
    base = {
        "instructions": "You can build charts.",
        "input": [{
            "id": "u-1", "kind": "input", "type": "message",
            "role": "user", "status": "completed",
            "content": [{"type": "text", "text": "Chart by category"}],
        }],
        "tools": [{
            "name": "add_widget", "description": "Add a widget",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            },
        }],
        "toolChoice": "auto",
        "responseFormat": {"type": "text"},
    }
    base.update(changes)
    return base


def ready(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_user_ids", "test-user-a")
    monkeypatch.setattr(settings, "studio_agent_enabled", True)
    monkeypatch.setattr(settings, "studio_agent_model", "gemini/gemini-2.5-flash")


def fake_response(*, text="Created your chart", calls=None):
    return SimpleNamespace(
        id="fake-response",
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=text,
            tool_calls=calls or [],
        ))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=18, total_tokens=30),
    )


def test_admin_only_and_explicit_opt_in(client, token_factory, monkeypatch):
    settings=get_settings()
    monkeypatch.setattr(settings, "studio_agent_enabled", False)
    monkeypatch.setattr(settings, "studio_agent_model", "")
    assert client.get(ENDPOINT + "/status").status_code == 401
    assert client.post(ENDPOINT + "/turn", json=payload()).status_code == 401
    assert client.get(ENDPOINT + "/status", headers=headers(token_factory)).status_code == 403
    monkeypatch.setattr(settings, "admin_user_ids", "test-user-a")
    h=headers(token_factory)
    status=client.get(ENDPOINT + "/status", headers=h)
    assert status.status_code == 200
    assert status.json() == {"enabled": False, "provider": None}
    denied=client.post(ENDPOINT + "/turn", json=payload(), headers=h)
    assert denied.status_code == 503


def test_proxy_forwards_tool_schemas_and_model_returns_calls(client, token_factory, monkeypatch):
    ready(monkeypatch)
    seen=[]
    async def model(**kwargs):
        seen.append(kwargs)
        call=SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="add_widget", arguments='{"category":"coffee","unused":null}',
            ),
        )
        return fake_response(calls=[call])
    monkeypatch.setattr(agent,"_provider_completion",model)
    r=client.post(ENDPOINT + "/turn",json=payload(),headers=headers(token_factory))
    assert r.status_code==200,r.text
    result=r.json()
    assert result["status"]=="completed"
    assert result["usage"]["totalTokens"]==30
    assert len(result["output"])==2
    tool=result["output"][1]
    assert tool["type"]=="function_call"
    assert tool["callId"]=="call-1"
    assert tool["name"]=="add_widget"
    assert tool["arguments"]=='{"category": "coffee"}'
    assert seen[0]["model"]=="gemini/gemini-2.5-flash"
    assert seen[0]["tools"][0]["function"]["name"]=="add_widget"
    assert seen[0]["tool_choice"]=="auto"
    assert "Sandbox" in seen[0]["messages"][0]["content"]
    assert "Chart by category"==seen[0]["messages"][1]["content"]
    assert not any("GEMINI_API_KEY" in str(x) for x in seen[0].values())


def test_tool_history_replayed_as_openai_messages(client,token_factory,monkeypatch):
    ready(monkeypatch)
    seen=[]
    async def model(**kwargs):
        seen.append(kwargs)
        return fake_response(text="I updated the chart")
    monkeypatch.setattr(agent,"_provider_completion",model)
    base=payload()
    base["input"] += [
        {"kind":"output","type":"function_call","callId":"c-1",
         "name":"add_widget","arguments":'{"category":"coffee"}'},
        {"type":"function_call_output","callId":"c-1",
         "output":'{"success":true,"widgetId":"foo"}'},
        {"kind":"input","type":"message","role":"user",
         "content":[{"type":"text","text":"Now show tea"}]},
    ]
    response=client.post(ENDPOINT+"/turn",json=base,headers=headers(token_factory))
    assert response.status_code==200,response.text
    messages=seen[0]["messages"]
    assert messages[2]["role"]=="assistant"
    assert messages[2]["tool_calls"][0]["id"]=="c-1"
    assert messages[3]["role"]=="tool"
    assert messages[3]["tool_call_id"]=="c-1"
    assert messages[4]["content"]=="Now show tea"


def test_proxy_rejects_unsupported_content_and_tools(client,token_factory,monkeypatch):
    ready(monkeypatch)
    h=headers(token_factory)
    bad=payload(input=[{
        "type":"message","kind":"input","role":"user",
        "content":[{"type":"image","imageUrl":"https://example.com/a.png"}],
    }])
    assert client.post(ENDPOINT+"/turn",json=bad,headers=h).status_code==422
    bad=payload(tools=[{
        "kind":"provided","name":"web_search","provider":{"type":"web_search"},
    }])
    assert client.post(ENDPOINT+"/turn",json=bad,headers=h).status_code==422
    bad=payload(toolChoice={"name":"not_in_roster"})
    assert client.post(ENDPOINT+"/turn",json=bad,headers=h).status_code==422


def test_proxy_returns_provider_errors_without_leaking_secrets(client,token_factory,monkeypatch):
    ready(monkeypatch)
    async def failing(**kwargs):
        raise RuntimeError("gemini sensitive-secret-123")
    monkeypatch.setattr(agent,"_provider_completion",failing)
    response=client.post(ENDPOINT+"/turn",json=payload(),headers=headers(token_factory))
    assert response.status_code==502
    assert "sensitive-secret" not in response.text
