"""Selected-object pipeline contracts. Mock Meshy responses do not establish live generation quality."""
import base64
import io
import json
import struct

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import config, main, objects, store

REGION = {'x': .25, 'y': .1, 'width': .5, 'height': .8}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path / 'storage')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setenv('MESHY_API_KEY', '')
    monkeypatch.delenv('MESHY_MODEL', raising=False)
    with TestClient(main.app) as api: yield api


def create(client):
    output = io.BytesIO()
    Image.new('RGB', (200, 200), 'orange').save(output, 'PNG')
    response = client.post('/api/projects', files={'file': ('person-fixture.png', output.getvalue())})
    assert response.status_code == 201
    return response.json()


def test_subject_selection_crop_validation_and_persistence(client):
    project = create(client)
    response = client.put(f"/api/projects/{project['id']}/subject", json=REGION)
    assert response.status_code == 200
    selected = response.json()['subject']
    assert len(selected['token']) == 64
    crop = Image.open(io.BytesIO(client.get(selected['assets']['preview']).content))
    assert crop.size == (100, 160) and not crop.getexif()
    store.init()
    assert store.get_project(project['id'])['subject'] == selected
    for invalid in [{**REGION, 'x': .9}, {**REGION, 'width': .01}, {**REGION, 'y': -1}, {**REGION, 'height': 0}]:
        assert client.put(f"/api/projects/{project['id']}/subject", json=invalid).status_code == 422
    assert client.get(f"/api/projects/{project['id']}/files/subject?selection=../secret").status_code == 404
    assert client.get(project['assets']['image']).status_code == 200


def test_object_generation_requires_selection_consent_and_private_key(client, monkeypatch):
    project = create(client); url = f"/api/projects/{project['id']}/object-jobs"
    assert client.post(url, json={'allow_external_processing': True}).status_code == 422
    client.put(f"/api/projects/{project['id']}/subject", json=REGION)
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={'allow_external_processing': True}).status_code == 503
    monkeypatch.setenv('MESHY_API_KEY', 'fixture-private-key')
    caps = client.get('/api/capabilities')
    assert caps.json()['object_generation']['configured'] and 'fixture-private-key' not in caps.text
    payload = {'allow_external_processing': True, 'pose': 'a-pose'}
    queued = client.post(url, json=payload, headers={'Idempotency-Key': 'same-click'})
    assert queued.status_code == 202
    job = queued.json()
    assert job['parameters']['selection'] == REGION and job['parameters']['pose'] == 'a-pose'
    assert client.post(url, json=payload, headers={'Idempotency-Key': 'same-click'}).json()['id'] == job['id']
    with pytest.raises(ValueError): store.enqueue(project['id'], job_type='panorama')
    client.post('/api/jobs/' + job['id'] + '/cancel')
    assert store.get_job(job['id'])['status'] == 'cancelled'


def test_meshy_model_configuration_fails_cleanly(client, monkeypatch):
    project = create(client)
    client.put(f"/api/projects/{project['id']}/subject", json=REGION)
    monkeypatch.setenv('MESHY_MODEL', 'invalid-model')
    assert not client.get('/api/capabilities').json()['object_generation']['configured']
    assert client.post(f"/api/projects/{project['id']}/object-jobs", json={'allow_external_processing': True}).status_code == 503


def task(client, monkeypatch):
    monkeypatch.setenv('MESHY_API_KEY', 'private-test-key')
    project = create(client)
    return store.enqueue(project['id'], job_type='object', parameters={'selection': REGION, 'model': 'meshy-7.1', 'allow_external_processing': True, 'pose': 'preserve'})


def test_meshy_submission_poll_download_and_publication_contract(client, monkeypatch):
    job = task(client, monkeypatch); store.claim(); seen = []; states = iter(['PENDING', 'IN_PROGRESS', 'SUCCEEDED'])
    model = (store.ROOT / 'examples' / 'cesium-man.glb').read_bytes()
    def handler(request):
        seen.append((request.method, str(request.url)))
        if request.method == 'POST':
            assert request.headers['authorization'] == 'Bearer private-test-key'
            body = json.loads(request.content)
            assert body['ai_model'] == 'meshy-7.1' and body['target_formats'] == ['glb'] and body['should_texture']
            assert 'pose_mode' not in body
            crop = Image.open(io.BytesIO(base64.b64decode(body['image_url'].split(',')[1])))
            assert crop.size == (100, 160)
            return httpx.Response(202, json={'result': 'remote-task'})
        if request.url.host == 'assets.meshy.ai':
            assert 'authorization' not in request.headers
            return httpx.Response(200, content=model)
        assert store.get_job(job['id'])['remote_id'] == 'remote-task'
        return httpx.Response(200, json={'status': next(states), 'progress': 50, 'model_urls': {'glb': 'https://assets.meshy.ai/model.glb?signature=fixture'}, 'consumed_credits': 30})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        result = objects.run(job, lambda message: None, remote, poll_interval=0)
    store.update_job(job['id'], status='completed', result=json.dumps(result))
    assert sum(method == 'POST' for method, url in seen) == 1
    assert client.get(result['assets']['object_model']).content == model
    assert 'signature' not in client.get(result['assets']['object_manifest']).text
    assert store.get_project(job['project_id'])['object']['ai_generated']
    other = create(client)
    assert client.get(f"/api/projects/{other['id']}/files/object_model?job_id={job['id']}").status_code == 404
    assert client.get(f"/api/projects/{job['project_id']}/files/raw?job_id={job['id']}").status_code == 404


def test_failed_task_resumes_without_a_second_post(client, monkeypatch):
    job = task(client, monkeypatch)
    store.update_job(job['id'], status='failed', remote_id='saved-task', error='interrupted')
    assert client.post('/api/jobs/' + job['id'] + '/resume').status_code == 202
    resumed = store.claim()
    seen = []
    def handler(request):
        seen.append(request.method)
        if request.url.host == 'assets.meshy.ai': return httpx.Response(200, content=(store.ROOT / 'examples' / 'cesium-man.glb').read_bytes())
        return httpx.Response(200, json={'status': 'SUCCEEDED', 'model_urls': {'glb': 'https://assets.meshy.ai/model.glb'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        result = objects.run(resumed, lambda message: None, remote, poll_interval=0)
    assert 'POST' not in seen and result['remote_id'] == 'saved-task'


@pytest.mark.parametrize('status', [400, 401, 402, 403, 429, 500])
def test_meshy_rejection_is_redacted_and_not_resubmitted(client, monkeypatch, status):
    job = task(client, monkeypatch); requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={'message': 'private-test-key raw secret'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError) as error: objects.run(job, lambda message: None, remote)
    assert 'private-test-key' not in str(error.value) and len(requests) == 1


def test_cancelled_object_never_submits_and_running_cancel_deletes_remote(client, monkeypatch):
    job = task(client, monkeypatch); store.update_job(job['id'], cancel=1)
    with pytest.raises(ValueError, match='cancelled before'): objects.run(job, lambda message: None)
    store.update_job(job['id'], cancel=0); requests = []
    def handler(request):
        requests.append(request.method)
        if request.method == 'POST':
            store.update_job(job['id'], cancel=1)
            return httpx.Response(202, json={'result': 'cancel-me'})
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError, match='cancelled locally'): objects.run(store.get_job(job['id']), lambda message: None, remote)
    assert requests == ['POST', 'DELETE']


def test_glb_validation_and_asset_url_boundary():
    with pytest.raises(ValueError): objects.validate_glb(b'not a glb')
    model = (store.ROOT / 'examples' / 'cesium-man.glb').read_bytes()
    assert objects.validate_glb(model)['meshes']
    for url in ['http://assets.meshy.ai/model.glb', 'https://127.0.0.1/model.glb', 'https://assets.meshy.ai.evil.example/model.glb']:
        with pytest.raises(ValueError): objects.download_model(None, url)
    document = json.dumps({'meshes': [{}], 'scenes': [{}], 'buffers': [{'uri': 'https://external.invalid/mesh.bin'}]}).encode()
    document += b' ' * (-len(document) % 4)
    broken = struct.pack('<4sIIII', b'glTF', 2, 20 + len(document), len(document), 0x4E4F534A) + document
    with pytest.raises(ValueError, match='self-contained'): objects.validate_glb(broken)


def test_parallel_startup_migrates_existing_subject_data_without_loss(client):
    from concurrent.futures import ThreadPoolExecutor
    project = create(client)
    with store.connection() as db:
        db.execute('ALTER TABLE projects DROP COLUMN subject')
        db.execute('ALTER TABLE jobs DROP COLUMN remote_id')
    with ThreadPoolExecutor(max_workers=4) as executor:
        for result in executor.map(lambda _: store.init(), range(4)): pass
    assert store.get_project(project['id'])['subject'] is None
    assert store.get_project(project['id'])['name'] == project['name']
