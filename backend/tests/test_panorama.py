"""Panorama API contracts use explicit mocks; they do not validate live AI image quality."""
import base64
import io
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import config, main, panorama, store


def image_bytes(size=(128, 64)):
    stream = io.BytesIO()
    Image.new('RGB', size, 'green').save(stream, 'PNG')
    return stream.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path / 'storage')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_IMAGE_MODEL', raising=False)
    monkeypatch.delenv('OPENAI_IMAGE_TIMEOUT', raising=False)
    with TestClient(main.app) as api:
        yield api


def create(client, kind='photo', size=(128, 64)):
    response = client.post('/api/projects?kind=' + kind, files={'file': ('reference.png', image_bytes(size), 'image/png')})
    assert response.status_code == 201, response.text
    return response.json()


def test_import_panorama_durable_assets_and_invalid_ratio(client):
    project = create(client, 'panorama')
    assert project['kind'] == 'panorama' and project['depth'] is None
    assert not project['panorama']['ai_generated']
    store.init()
    assert store.get_project(project['id'])['panorama']['projection'] == 'equirectangular'
    assert client.get(project['panorama']['assets']['panorama']).status_code == 200
    assert client.post(f"/api/projects/{project['id']}/depth-jobs", json={}).status_code == 409
    invalid = client.post('/api/projects?kind=panorama', files={'file': ('flat.png', image_bytes((90, 60)))})
    assert invalid.status_code == 422 and '2:1' in invalid.text
    assert client.get('/api/projects').json()['total'] == 1


def test_panorama_import_allows_large_image_without_changing_photo_limit(client):
    assert client.post('/api/projects', files={'file': ('large.png', image_bytes((4098, 2049)))}).status_code == 422
    assert create(client, 'panorama', (4098, 2049))['width'] == 4098


def test_consent_key_status_and_queue_separation(client, monkeypatch):
    project = create(client)
    url = f"/api/projects/{project['id']}/panorama-jobs"
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={'allow_external_processing': True}).status_code == 503
    assert not client.get('/api/capabilities').json()['panorama_generation']['configured']
    monkeypatch.setenv('OPENAI_API_KEY', 'private-fixture-not-real')
    status = client.get('/api/capabilities')
    assert status.json()['panorama_generation']['configured'] and 'private-fixture' not in status.text
    payload = {'allow_external_processing': True, 'description': 'forest', 'quality': 'low'}
    response = client.post(url, json=payload, headers={'Idempotency-Key': 'one-explicit-request'})
    assert response.status_code == 202
    job = response.json()
    assert job['job_type'] == 'panorama' and job['parameters']['description'] == 'forest'
    assert client.post(url, json=payload, headers={'Idempotency-Key': 'one-explicit-request'}).json()['id'] == job['id']
    with pytest.raises(ValueError): store.enqueue(project['id'], 'one-explicit-request')
    with pytest.raises(ValueError): store.enqueue(project['id'])
    assert client.post('/api/jobs/' + job['id'] + '/cancel').json()['status'] == 'cancelled'
    store.enqueue(project['id'])  # A cancelled panorama does not prevent a later depth job.


def test_private_config_parsing_and_model_validation(client, tmp_path):
    (tmp_path / '.env').write_text('# private\nOPENAI_API_KEY="fixture-key"\nOPENAI_IMAGE_TIMEOUT=700\nIGNORED=anything\n', encoding='utf-8')
    assert config.openai_config()['api_key'] == 'fixture-key'
    assert config.openai_config()['timeout'] == 600
    (tmp_path / '.env').write_text('OPENAI_IMAGE_MODEL=unsupported', encoding='utf-8')
    response = client.get('/api/capabilities').json()['panorama_generation']
    assert not response['configured'] and response['error']


def test_openai_multipart_contract_and_validated_image():
    seen = []
    def handler(request):
        seen.append(request)
        body = request.read()
        assert request.url == 'https://api.openai.com/v1/images/edits'
        assert request.headers['authorization'] == 'Bearer mock-secret'
        assert b'name="image[]"' in body and b'2048x1024' in body
        assert b'equirectangular' in body and b'No multiple panels' in body
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image_bytes()).decode()}], 'usage': {'total_tokens': 12}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        image, usage = panorama.request_image(b'reference-fixture', 'pine forest', 'medium', {'api_key': 'mock-secret', 'model': 'gpt-image-2', 'timeout': 30}, client)
    assert image.size == (128, 64) and usage['total_tokens'] == 12 and len(seen) == 1


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_remote_errors_are_redacted_and_never_retried(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': 'mock-secret diagnostic'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError) as error:
            panorama.request_image(b'fixture', '', 'medium', {'api_key': 'mock-secret', 'model': 'gpt-image-2'}, client)
    assert 'mock-secret' not in str(error.value) and len(calls) == 1


def test_non_panorama_output_and_timeout_do_not_retry():
    def invalid(request):
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image_bytes((90, 60))).decode()}]})
    with httpx.Client(transport=httpx.MockTransport(invalid)) as client:
        with pytest.raises(ValueError, match='valid 2:1'): panorama.request_image(b'fixture', '', 'low', {'api_key': 'fixture', 'model': 'gpt-image-2'}, client)
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('mock-secret', request=request)
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ValueError, match='no automatic retry') as error: panorama.request_image(b'fixture', '', 'low', {'api_key': 'fixture', 'model': 'gpt-image-2'}, client)
    assert len(calls) == 1 and 'mock-secret' not in str(error.value)


def test_panorama_job_publication_ownership_and_cancellation(client, monkeypatch):
    first, second = create(client), create(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture')
    calls = []
    def mocked_request(*args):
        calls.append(args)
        return Image.new('RGB', (128, 64), 'blue'), {'fixture': True}
    monkeypatch.setattr(panorama, 'request_image', mocked_request)
    job = store.enqueue(first['id'], job_type='panorama', parameters={'allow_external_processing': True})
    store.claim()
    result = panorama.run(job, lambda message: None)
    store.update_job(job['id'], status='completed', result=json.dumps(result))
    assert store.get_project(first['id'])['depth'] is None
    assert client.get(result['assets']['panorama']).status_code == 200
    assert client.get(result['assets']['panorama_manifest']).json()['ai_generated']
    assert client.get(f"/api/projects/{second['id']}/files/panorama?job_id={job['id']}").status_code == 404
    assert client.get(f"/api/projects/{first['id']}/files/raw?job_id={job['id']}").status_code == 404
    depth = store.enqueue(first['id'])
    store.update_job(depth['id'], status='completed', result=json.dumps({'job_id': depth['id']}))
    assert store.get_project(first['id'])['panorama']['job_id'] == job['id']
    cancelled = store.enqueue(second['id'], job_type='panorama', parameters={'allow_external_processing': True})
    store.update_job(cancelled['id'], cancel=1)
    with pytest.raises(ValueError, match='cancelled before'): panorama.run(cancelled, lambda message: None)
    assert len(calls) == 1


def test_v1_schema_migration_preserves_projects(client):
    project = create(client)
    job = store.enqueue(project['id'])
    with store.connection() as db:
        db.execute('ALTER TABLE projects DROP COLUMN kind')
        db.execute('ALTER TABLE jobs DROP COLUMN job_type')
        db.execute('ALTER TABLE jobs DROP COLUMN parameters')
        db.execute('PRAGMA user_version=1')
    store.init()
    assert store.get_project(project['id'])['kind'] == 'photo'
    assert store.get_job(job['id'])['job_type'] == 'depth'
    assert store.project_dir(project['id']).joinpath('image.jpg').exists()
