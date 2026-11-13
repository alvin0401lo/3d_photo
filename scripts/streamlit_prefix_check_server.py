"""Local test fixture for Cloud's stripped /~/+/ prefix; run with uvicorn."""
from starlette.responses import HTMLResponse

from streamlit_app import app as upstream


async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        await upstream(scope, receive, send)
        return
    prefix = '/~/+'
    path = scope['path']
    if path == prefix or path.startswith(prefix + '/'):
        path = path[len(prefix):] or '/'
        # Community Cloud removes the prefix without setting ASGI root_path.
        await upstream({**scope, 'path': path, 'raw_path': path.encode(), 'root_path': ''}, receive, send)
    elif scope['type'] == 'http':
        await HTMLResponse('<h1>Hosting platform: application paths require /~/+/</h1>')(scope, receive, send)
    else:
        await send({'type': 'websocket.close', 'code': 1008})
