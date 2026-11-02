import logging
from aiohttp import web
from nodes import MAX_RESOLUTION
from server import PromptServer
from .compiler import preview
from .state import strict_load, StateError, fail

async def preview_request(request):
    try:
        body=bytearray()
        async for chunk in request.content.iter_chunked(16384):
            body.extend(chunk)
            if len(body)>262144:
                return web.json_response({'error':{'code':'E_STATE_SIZE','path':'request'}},status=413)
        try:
            data=strict_load(body.decode('utf-8'))
        except UnicodeDecodeError:
            fail('E_UNICODE','request')
        if type(data) is not dict or set(data)!={'state_json'}:
            fail('E_KEYS','request')
        result=preview(data['state_json'],MAX_RESOLUTION)
        result['max_resolution']=min(16384,MAX_RESOLUTION)
        return web.json_response(result)
    except StateError as error:
        return web.json_response({'error':{'code':error.code,'path':error.path,'details':error.details}},status=413 if error.code=='E_STATE_SIZE' else 400)
    except Exception:
        logging.exception('Anima sheet preview failed')
        return web.json_response({'error':{'code':'E_INTERNAL','path':'preview'}},status=500)

def register_preview():
    PromptServer.instance.routes.post('/anima_character_sheet_designer/v1/preview')(preview_request)
    from .tagger_download import register_routes
    register_routes(PromptServer.instance.routes)
