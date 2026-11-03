"""Small background acquisition service; generation never starts a UI download."""
from threading import RLock, Thread
from time import monotonic
from urllib.parse import urlsplit
from .tagger_contracts import model_spec
from .tagger_models import model_files, download_model, required_files, roots, download_info
from .state import StateError

_jobs={}
_checked_at={}
_lock=RLock()
_busy={'checking','downloading','verifying'}
STATUS_TTL=5.0

def _base(model):
    own,_=roots()
    return dict(model_id=model['id'],state='checking',completed=0,total=sum(f['size'] for f in required_files(model)),
                path=str(own/model['id']),filename='',error='')

def _update(model_id,**values):
    with _lock: _jobs[model_id].update(values)

def _work(model,download,refresh=False):
    model_id=model['id']
    try:
        try: directory=model_files(model,False,refresh=refresh)
        except StateError as error:
            if error.code!='E_MODEL_MISSING': raise
            if not download:
                _update(model_id,state='missing'); return
            directory=download_model(model,lambda phase,completed,total,filename:
                _update(model_id,state=phase,completed=completed,total=total,filename=filename))
        _update(model_id,state='ready',path=str(directory),completed=sum(f['size'] for f in required_files(model)),**download_info(directory,model))
    except Exception as error:
        _update(model_id,state='error',error=str(error)[:500])
    finally:
        with _lock: _checked_at[model_id]=monotonic()

def status(model_id,download=False,refresh=False):
    model=model_spec(model_id)
    with _lock:
        previous=_jobs.get(model_id)
        if previous and previous['state'] in _busy: return dict(previous)
        if previous and not download and not refresh and monotonic()-_checked_at.get(model_id,0)<STATUS_TTL:
            return dict(previous)
        if download and any(j['state'] in ('downloading','verifying') for j in _jobs.values()):
            return dict(_base(model),state='busy')
        _jobs[model_id]=_base(model)
        Thread(target=_work,args=(model,download,refresh),daemon=True,name='anima-tagger-model').start()
        return dict(_jobs[model_id])

async def model_request(request):
    from aiohttp import web
    # A download is a POST action, never an inference setting or a GET side effect.
    if request.method=='POST':
        origin=request.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=request.host:
            return web.json_response({'error':'Cross-origin download is not allowed.'},status=403)
    try: return web.json_response(status(request.match_info['model_id'],request.method=='POST',request.query.get('refresh')=='1'))
    except StateError as error: return web.json_response({'error':str(error)},status=400)

def register_routes(routes):
    routes.get('/anima_character_sheet_designer/v1/models/{model_id}')(model_request)
    routes.post('/anima_character_sheet_designer/v1/models/{model_id}/download')(model_request)
