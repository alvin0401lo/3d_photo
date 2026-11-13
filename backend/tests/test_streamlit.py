"""Hosted-origin boundaries and the native Streamlit shell; provider calls remain opt-in."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path / 'storage')
    with TestClient(main.app) as api: yield api


def test_hosted_api_accepts_same_origin_and_rejects_other_or_malformed_origins(client, monkeypatch):
    monkeypatch.setenv('DEPTHFRAME_SAME_ORIGIN', '1')
    headers = {'Host': '127.0.0.1:8501', 'Origin': 'http://127.0.0.1:8501'}
    assert client.post('/api/examples', headers=headers).status_code == 201
    for origin in ['https://evil.example', 'null', 'http://[', 'http://127.0.0.1:8501/?query=bad']:
        assert client.post('/api/examples', headers={**headers, 'Origin': origin}).status_code == 403
    monkeypatch.setenv('DEPTHFRAME_HOSTED', '1')
    assert client.post('/api/examples', headers=headers).status_code == 201
    assert client.post('/api/examples', headers={**headers, 'Origin': 'http://localhost:5173'}).status_code == 403
    monkeypatch.delenv('DEPTHFRAME_SAME_ORIGIN')
    assert client.post('/api/examples', headers=headers).status_code == 403


def test_streamlit_shell_renders_without_keys_or_provider_requests():
    AppTest = pytest.importorskip('streamlit.testing.v1').AppTest
    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / 'streamlit_ui.py')).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == 'DepthFrame AI'
    assert app.get('iframe')[0].proto.src == '/workspace/'
    assert 'private' in ' '.join(item.value for item in app.caption).lower()
