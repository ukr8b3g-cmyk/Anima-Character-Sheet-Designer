"""Bounded ORT execution. Never retain an InferenceSession or GPU tensor."""
import gc
import time
from collections import OrderedDict
from threading import RLock
from .state import fail
from .tagger_contracts import canonical
from .tagger_models import interrupt

_cache=OrderedDict()
_unavailable={}
_lock=RLock()

class ProviderUnavailable(RuntimeError): pass

def fallback_reason(exc):
    text=str(exc).lower()
    if any(x in text for x in ('illegal memory access','device-side assert','unspecified launch failure')): return None
    if isinstance(exc,ProviderUnavailable): return 'cuda_provider_unavailable'
    if 'out of memory' in text or 'cudaerrormemoryallocation' in text: return 'cuda_oom'
    if any(x in text for x in ('disable_cpu_ep_fallback','assigned to the default cpu ep','not implemented','could not find an implementation','failed to find kernel')): return 'cuda_graph_unsupported'
    if any(x in text for x in ('cudaexecutionprovider','onnxruntime_providers_cuda','cudnn64','cublas64','cuda driver version is insufficient','cuda failure 100','cuda failure 35')): return 'cuda_initialization_failed'
    return None

def fingerprint(ort,device_id,device='auto'):
    import torch
    value=dict(ort=ort.__version__,providers=ort.get_available_providers(),device_id=device_id,torch=torch.__version__,cuda=torch.version.cuda)
    if device!='cpu' and torch.cuda.is_available():
        if device_id>=torch.cuda.device_count(): fail('E_DEVICE_ID','device_id')
        p=torch.cuda.get_device_properties(device_id)
        value.update(gpu=p.name,total_memory=p.total_memory,capability=[p.major,p.minor])
        # Driver version is part of the unavailable/cache fingerprint where exposed.
        try:
            import pynvml
            pynvml.nvmlInit()
            try: value['driver']=pynvml.nvmlSystemGetDriverVersion()
            finally: pynvml.nvmlShutdown()
        except ImportError: value['driver']='unavailable'
        except pynvml.NVMLError: value['driver']='unavailable'
    return canonical(value)

def validate_scores(value,count):
    import numpy as np
    if value.shape!=(1,count) or value.dtype.kind!='f': fail('E_ONNX_SIGNATURE','prediction')
    if not np.isfinite(value).all() or (value < -1e-6).any() or (value > 1+1e-6).any(): fail('E_INVALID_SCORE','prediction')
    return np.clip(value[0],0,1).astype(np.float32,copy=True)

def run_session(ort,path,model,tensor,device,device_id):
    session=None
    diagnostic={}
    try:
        interrupt(); options=ort.SessionOptions(); options.intra_op_num_threads=4
        if device=='cuda':
            if 'CUDAExecutionProvider' not in ort.get_available_providers(): raise ProviderUnavailable('CUDA EP missing')
            # ORT assigns shape/unsupported operators to CPU even in valid CUDA graphs.
            providers=[('CUDAExecutionProvider',{'device_id':device_id}), 'CPUExecutionProvider']
        else: providers=['CPUExecutionProvider']
        start=time.perf_counter()
        session=ort.InferenceSession(str(path),sess_options=options,providers=providers)
        session.disable_fallback()
        actual=session.get_providers()
        if device=='cuda' and (not actual or actual[0]!='CUDAExecutionProvider'): raise ProviderUnavailable(f'CUDA session was replaced by {actual}')
        ins,outs=session.get_inputs(),session.get_outputs()
        if len(ins)!=1 or len(outs)!=1: fail('E_ONNX_SIGNATURE','model')
        inp,out=ins[0],outs[0]
        if inp.name!=model['input']['name'] or out.name!=model['output']['name'] or inp.type!='tensor(float)' or out.type!='tensor(float)': fail('E_ONNX_SIGNATURE','model')
        if list(inp.shape[1:])!=model['input']['shape'][1:] or list(out.shape[1:])!=model['output']['shape'][1:]: fail('E_ONNX_SIGNATURE','model')
        interrupt(); loaded=time.perf_counter()
        y=session.run([out.name],{inp.name:tensor})[0]
        interrupt()
        diagnostic.update(actual_device=device,providers=actual,load_seconds=round(loaded-start,4),inference_seconds=round(time.perf_counter()-loaded,4))
        return validate_scores(y,model['metadata']['rows']),diagnostic
    finally:
        release_start=time.perf_counter()
        if session is not None: del session
        gc.collect()
        diagnostic['release_seconds']=round(time.perf_counter()-release_start,4)

def infer(directory,model,rgb,image_hash,device,device_id=0,refresh_nonce=0):
    try: import onnxruntime as ort
    except ImportError: fail('E_ORT_MISSING','onnxruntime','Install a compatible ONNX Runtime in the ComfyUI environment for image tagging.')
    except OSError as exc: fail('E_ORT_ENVIRONMENT','onnxruntime',str(exc))
    from .image_utils import preprocess
    if device not in ('auto','cuda','cpu'): fail('E_TAGGER_DEVICE','device')
    # Import torch first so the installed CUDA/cuDNN DLLs are discoverable by ORT.
    fp=fingerprint(ort,device_id,device)
    failure_key=(model['sha256'],fp)
    key=(image_hash,model['sha256'],model['preprocess_revision'],fp,device,refresh_nonce)
    with _lock:
        interrupt()
        if key in _cache:
            scores,diagnostic=_cache.pop(key); _cache[key]=(scores,diagnostic)
            return scores.copy(),dict(diagnostic,cache_hit=True,load_seconds=0,preprocess_seconds=0,inference_seconds=0,release_seconds=0)
        preprocess_start=time.perf_counter()
        tensor=preprocess(rgb,model['id'])
        preprocess_seconds=round(time.perf_counter()-preprocess_start,4)
        reason=None
        known=_unavailable.get(failure_key)
        if device=='auto' and known and known[0]==refresh_nonce: reason=known[1]
        if device!='cpu' and not reason:
            try:
                scores,diagnostic=run_session(ort,directory/model['filename'],model,tensor,'cuda',device_id)
            except (RuntimeError,ort.capi.onnxruntime_pybind11_state.Fail,ort.capi.onnxruntime_pybind11_state.NotImplemented,ort.capi.onnxruntime_pybind11_state.RuntimeException) as exc:
                interrupt(); reason=fallback_reason(exc)
                if device=='cuda':
                    code='E_GPU_UNAVAILABLE' if reason in ('cuda_provider_unavailable','cuda_initialization_failed') else 'E_GPU_EXECUTION'
                    fail(code,'device',str(exc))
                if reason is None: raise
                if reason!='cuda_oom': _unavailable[failure_key]=(refresh_nonce,reason)
                print(f'[Anima Tagger] {reason}; using the SAME {model["id"]} model on CPU.',flush=True)
        if device=='cpu' or reason:
            interrupt()
            scores,diagnostic=run_session(ort,directory/model['filename'],model,tensor,'cpu',device_id)
        diagnostic.update(requested_device=device,fallback_reason=reason,cache_hit=False,model_sha256=model['sha256'],backend_fingerprint=fp,session_released=True,preprocess_seconds=preprocess_seconds)
        interrupt(); _cache[key]=(scores,diagnostic)
        while len(_cache)>8 or sum(v[0].nbytes for v in _cache.values())>32*1024*1024: _cache.popitem(last=False)
        return scores.copy(),dict(diagnostic)

def clear_cache():
    with _lock: _cache.clear(); _unavailable.clear()
