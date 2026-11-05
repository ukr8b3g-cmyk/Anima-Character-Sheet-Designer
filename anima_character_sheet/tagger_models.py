"""Pinned model discovery and selected-model acquisition in image mode."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from .state import fail

_verified={}
_refresh={}
_lock=RLock()
_download_lock=RLock()

def interrupt():
    try: from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError: return
    throw_exception_if_processing_interrupted()

def file_hash(path,refresh=False):
    path=Path(path)
    stat=path.stat(); key=(str(path.resolve()),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    with _lock:
        if not refresh and key in _verified: return _verified[key]
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while block:=stream.read(4*1024*1024):
                interrupt(); digest.update(block)
        result=digest.hexdigest()
        if len(_verified)>64: _verified.clear()
        _verified[key]=result
        return result

def required_files(model):
    return [dict(filename=model['filename'],sha256=model['sha256'],size=model['size']),model['metadata']]+([model['preprocess_metadata']] if 'preprocess_metadata' in model else [])

def roots():
    import folder_paths
    own=Path(folder_paths.models_dir)/'anima_tagger'
    candidates=[own]
    for key in ('anima_tagger','booru_tagger','wd14_tagger'):
        try: candidates.extend(Path(p) for p in folder_paths.get_folder_paths(key))
        except KeyError: pass
    candidates += [Path(folder_paths.models_dir)/'booru_tagger',Path(folder_paths.models_dir)/'wd14_tagger']
    return own,list(dict.fromkeys(p.resolve() for p in candidates))

def model_files(model,allow_download=False,refresh=False):
    own,search=roots(); required=required_files(model)
    for root in search:
        # Only bounded, model-specific paths; never recursively scan model drives.
        for directory in (root/model['id'],root/model['repo_id'].split('/')[-1],root):
            if not all((directory/f['filename']).is_file() for f in required): continue
            valid=all((directory/f['filename']).stat().st_size==f['size'] and file_hash(directory/f['filename'],refresh)==f['sha256'] for f in required)
            if valid: return directory
            if directory==own.resolve()/model['id']: fail('E_MODEL_HASH',str(directory),'Pinned model/metadata mismatch. Existing files were not replaced.')
    if not allow_download: fail('E_MODEL_MISSING',model['id'],f"Install the pinned files in {own/model['id']} or use Download selected model.")
    return download_model(model)

def download_model(model,progress=None):
    # UI preparation and queued inference share one acquisition path.
    with _download_lock:
        return _download_model(model,progress)

def _download_model(model,progress=None):
    """Explicit acquisition of manifest-pinned files; never replace existing weights."""
    from urllib.request import Request, urlopen
    own,_=roots(); required=required_files(model)
    destination=own/model['id']; destination.mkdir(parents=True,exist_ok=True)
    total=sum(f['size'] for f in required); completed=0; downloaded=False
    def report(phase,received=0,filename=''):
        if progress: progress(phase,completed+received,total,filename)
    for f in required:
        final=destination/f['filename']
        if final.exists():
            if final.stat().st_size!=f['size'] or file_hash(final,True)!=f['sha256']: fail('E_MODEL_HASH',str(final))
            completed+=f['size']; report('verifying',filename=f['filename'])
            continue
        interrupt(); print(f"[Anima Tagger] Downloading {model['id']}/{f['filename']}",flush=True)
        url=f"https://huggingface.co/{model['repo_id']}/resolve/{model['revision']}/{f['filename']}"
        part=destination/(f['filename']+'.download.part'); received=0
        try:
            report('downloading',filename=f['filename'])
            with urlopen(Request(url,headers={'User-Agent':'Anima-Character-Sheet-Designer'}),timeout=30) as response, part.open('wb') as output:
                while block:=response.read(1024*1024):
                    interrupt(); received+=len(block)
                    if received>f['size']: fail('E_MODEL_SIZE',f['filename'])
                    output.write(block); report('downloading',received,f['filename'])
            report('verifying',received,f['filename'])
            if received!=f['size'] or file_hash(part,True)!=f['sha256']: fail('E_MODEL_HASH',str(part))
            # Refuse to overwrite a file created while the download was running.
            if final.exists(): fail('E_MODEL_EXISTS',str(final))
            part.rename(final); completed+=received; downloaded=True
        finally:
            if part.exists(): part.unlink()
    if downloaded:
        receipt=destination/'.anima-download.json'
        temporary=destination/'.anima-download.json.part'
        temporary.write_text(json.dumps(dict(model_sha256=model['sha256'],revision=model['revision'],downloaded_at=datetime.now(timezone.utc).isoformat())),encoding='utf-8')
        temporary.replace(receipt)
    report('ready')
    return destination

def download_info(directory,model):
    """Only a completed downloader receipt proves acquisition time."""
    directory=Path(directory); downloaded_at=None; modified_at=None
    try:
        receipt=directory/'.anima-download.json'
        if receipt.stat().st_size<4096:
            data=json.loads(receipt.read_text('utf-8'))
            if data.get('model_sha256')==model['sha256'] and data.get('revision')==model['revision']:
                value=data['downloaded_at']; parsed=datetime.fromisoformat(value)
                if parsed.tzinfo is not None: downloaded_at=parsed.isoformat()
    except (OSError,ValueError,KeyError,TypeError): pass
    try: modified_at=datetime.fromtimestamp((directory/model['filename']).stat().st_mtime,timezone.utc).isoformat()
    except OSError: pass
    return dict(downloaded_at=downloaded_at,file_modified_at=modified_at)

def refresh_model(model,nonce):
    """Explicit refresh invalidates stat-memoized hashes once per nonce."""
    with _lock:
        previous=_refresh.get(model['id'],0)
        if nonce!=previous:
            _verified.clear()
        _refresh[model['id']]=nonce

def read_tags(directory,model):
    with (directory/model['metadata']['filename']).open('r',encoding='utf-8-sig',newline='') as file:
        reader=csv.DictReader(file)
        if not {'name','category'}<=set(reader.fieldnames or []): fail('E_TAG_CSV','selected_tags.csv')
        rows=list(reader)
    if len(rows)!=model['metadata']['rows']: fail('E_TAG_COUNT','selected_tags.csv')
    seen=set(); tags=[]
    for i,row in enumerate(rows):
        name=row['name']
        if not name or name in seen or len(name)>256 or row['category'] not in model['categories']: fail('E_TAG_CSV',str(i))
        seen.add(name); tags.append(dict(name=name,category=int(row['category']),index=i))
    return tags
