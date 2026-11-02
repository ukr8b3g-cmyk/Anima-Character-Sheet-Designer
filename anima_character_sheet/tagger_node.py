"""Public lazy manual/image switch. OFF has no image or ML dependency."""
import time
import uuid
from .state import fail, StateError
from .tagger_contracts import canonical, config, manual_text, model_spec, resource

DEFAULT_CONFIG=canonical(resource('contracts/default_tagger_config.json'))

def effective_config(raw, include_character=None, include_copyright=None, allow_multiple_subjects=None):
    """Native inputs take precedence; old API graphs retain their saved JSON values."""
    cfg=config(raw)
    for key,value in (('include_character',include_character),('include_copyright',include_copyright)):
        if value is not None:
            if type(value) is not bool: fail('E_TYPE',key)
            cfg[key]=value
    if allow_multiple_subjects is not None:
        if type(allow_multiple_subjects) is not bool: fail('E_TYPE','allow_multiple_subjects')
        cfg['multi_subject_policy']='allow_with_warning' if allow_multiple_subjects else 'block'
    return cfg

class AnimaImageTagger:
    CATEGORY='Anima/Character Sheet'
    FUNCTION='tag'
    RETURN_TYPES=('STRING','STRING','STRING','STRING')
    RETURN_NAMES=('prompt','profile_json','raw_tags_json','diagnostics')
    DESCRIPTION='Select unchanged manual text or local image-to-tags. Images become text, not a visual reference. Downloads are opt-in.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'use_image':('BOOLEAN',{'default':False,'label_on':'Image tags','label_off':'Manual text'}),
            'model_id':([m['id'] for m in resource('contracts/models.v1.json')['models']],),'device':(['auto','cuda','cpu'],),
            'config_json':('STRING',{'default':DEFAULT_CONFIG,'multiline':True,'dynamicPrompts':False}),
            'allow_download':('BOOLEAN',{'default':False})},
            'optional':{'manual_prompt':('STRING',{'forceInput':True,'lazy':True}),'image':('IMAGE',{'lazy':True}),'mask':('MASK',{'lazy':True}),
            'include_character':('BOOLEAN',{'default':False,'tooltip':'Include detected character names in portrait/body prompts. Default OFF.'}),
            'include_copyright':('BOOLEAN',{'default':False,'tooltip':'Include detected series names in portrait/body prompts. Default OFF.'}),
            'allow_multiple_subjects':('BOOLEAN',{'default':False,'tooltip':'Allow multiple detected subjects. Their appearance may mix. Default OFF.'})}}

    def check_lazy_status(self,use_image=False,**kwargs):
        if type(use_image) is not bool: fail('E_TYPE','use_image')
        if not use_image:
            if 'manual_prompt' not in kwargs: fail('E_PROMPT_EMPTY','manual_prompt')
            return ['manual_prompt'] if kwargs['manual_prompt'] is None else []
        if 'image' not in kwargs: fail('E_IMAGE_MISSING','image','Connect Load Image to the image input.')
        return [k for k in ('image','mask') if k in kwargs and kwargs[k] is None]

    @classmethod
    def VALIDATE_INPUTS(cls,use_image=False,manual_prompt=None,config_json=DEFAULT_CONFIG,model_id='pixai_v1_fp16',device='auto'):
        try:
            # Connected values are unavailable during ComfyUI's preflight.
            # Defer selected-branch validation until the Boolean is evaluated.
            if use_image is None: return True
            if type(use_image) is not bool: fail('E_TYPE','use_image')
            if not use_image:
                if isinstance(manual_prompt,str): manual_text(manual_prompt)
                return True
            config(config_json); model_spec(model_id)
            if device not in ('auto','cuda','cpu'): fail('E_TAGGER_DEVICE','device')
            return True
        except StateError as exc: return str(exc)

    @classmethod
    def IS_CHANGED(cls,use_image=False,manual_prompt=None,**kwargs):
        # A linked Boolean is unknown here. Execute the cheap switch each queue;
        # the image branch has its own content-based inference cache.
        if use_image is None: return 'linked-switch:'+uuid.uuid4().hex
        if not use_image: return ('manual',manual_prompt)
        from .tagger_models import model_files, required_files, file_hash, refresh_model
        cfg=effective_config(kwargs.get('config_json',DEFAULT_CONFIG),*[kwargs.get(k) for k in ('include_character','include_copyright','allow_multiple_subjects')]); model=model_spec(kwargs.get('model_id','pixai_v1_fp16'))
        refresh_model(model,cfg['refresh_nonce'])
        try:
            directory=model_files(model,False)
            files=[file_hash(directory/f['filename']) for f in required_files(model)]
        except StateError: files=['unavailable']
        return canonical(dict(config=cfg,model=model['id'],files=files,device=kwargs.get('device'),download=kwargs.get('allow_download')))

    def tag(self,use_image=False,model_id='pixai_v1_fp16',device='auto',config_json=DEFAULT_CONFIG,allow_download=False,manual_prompt=None,image=None,mask=None,include_character=None,include_copyright=None,allow_multiple_subjects=None,**legacy):
        if type(use_image) is not bool: fail('E_TYPE','use_image')
        if not use_image:
            text=manual_text(manual_prompt)
            status=dict(mode='manual',actual_device=None,cache_hit=False,analysis_performed=False)
            return {'ui':{'anima_tagger_status':[status],'anima_tagger_text':[text]},'result':(text,'','',canonical(status))}
        from .image_utils import tensor_rgb, pixel_hash
        from .tagger_models import model_files, read_tags, interrupt, refresh_model
        from .tagger_backend import infer
        from .tagger_profile import build_profile
        start=time.perf_counter(); interrupt()
        cfg=effective_config(config_json,include_character,include_copyright,allow_multiple_subjects); model=model_spec(model_id)
        if image is None: fail('E_IMAGE_MISSING','image','Connect Load Image to the image input. Embedded filename loading has been removed.')
        rgb=tensor_rgb(image,mask)
        image_hash=pixel_hash(rgb); refresh_model(model,cfg['refresh_nonce'])
        directory=model_files(model,allow_download); tags=read_tags(directory,model)
        probabilities,diagnostic=infer(directory,model,rgb,image_hash,device,cfg['device_id'],cfg['refresh_nonce'])
        del rgb
        scored=[dict(tag,score=float(score)) for tag,score in zip(tags,probabilities,strict=True)]
        filter_start=time.perf_counter()
        text,p,filtered=build_profile(scored,cfg,model,image_hash)
        diagnostic.update(mode='image_tags',model_id=model_id,total_seconds=round(time.perf_counter()-start,4),image_hash=image_hash,review_count=p['review_count'],multiple_subjects=filtered['multiple_subjects'],filter_seconds=round(time.perf_counter()-filter_start,4))
        # Compact, lossless row order with self-describing columns; no top-k truncation.
        raw=canonical(dict(model_id=model_id,image_hash=image_hash,columns=['name','category','score'],tags=[[t['name'],t['category'],round(float(s),8)] for t,s in zip(tags,probabilities,strict=True)],excluded=filtered['excluded'],review=filtered['review']))
        if len(raw.encode('utf-8'))>2*1024*1024: fail('E_RAW_TAG_LIMIT','raw_tags_json')
        status=dict(diagnostic,groups=p['groups'],user_additions=p['user_additions'],identity_labels=p['identity_labels'],excluded=filtered['excluded'],review=filtered['review'])
        interrupt()
        return {'ui':{'anima_tagger_status':[status],'anima_tagger_text':[text]},'result':(text,canonical(p),raw,canonical(diagnostic))}
