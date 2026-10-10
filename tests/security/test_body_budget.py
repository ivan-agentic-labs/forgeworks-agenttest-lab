import asyncio
from fastapi.testclient import TestClient
from agenttest_lab.main import create_app
from agenttest_lab.presentation.body_budget import BodyBudgetMiddleware


def test_oversized_body_rejected_before_json(tmp_path):
    with TestClient(create_app(str(tmp_path / 'body.sqlite'))) as client:
        response = client.post('/v1/evaluation-runs', content=b'x' * (8 * 1024 * 1024 + 1), headers={'Content-Type': 'application/json'})
        assert response.status_code == 413
        assert response.json()['code'] == 'REQUEST_BODY_TOO_LARGE'


def test_chunked_oversized_body_stops_before_application():
    async def scenario():
        called = False
        async def app(scope, receive, send):
            nonlocal called
            called = True
        messages = iter([{'type':'http.request','body':b'123','more_body':True}, {'type':'http.request','body':b'456','more_body':False}])
        sent = []
        async def receive(): return next(messages)
        async def send(message): sent.append(message)
        await BodyBudgetMiddleware(app, max_bytes=5)({'type':'http'}, receive, send)
        assert not called
        assert sent[0]['status'] == 413
    asyncio.run(scenario())


def test_exact_chunked_budget_is_replayed_once():
    async def scenario():
        messages = iter([{'type':'http.request','body':b'12','more_body':True}, {'type':'http.request','body':b'345','more_body':False}, {'type':'http.disconnect'}])
        async def receive(): return next(messages)
        async def send(message): pass
        async def app(scope, receive, send):
            assert await receive() == {'type':'http.request','body':b'12345','more_body':False}
            assert await receive() == {'type':'http.disconnect'}
        await BodyBudgetMiddleware(app, max_bytes=5)({'type':'http'}, receive, send)
    asyncio.run(scenario())


def test_disconnect_does_not_invoke_application():
    async def scenario():
        async def receive(): return {'type':'http.disconnect'}
        async def send(message): raise AssertionError('No response on disconnect')
        async def app(scope, receive, send): raise AssertionError('Disconnected client')
        await BodyBudgetMiddleware(app)({'type':'http'}, receive, send)
    asyncio.run(scenario())
