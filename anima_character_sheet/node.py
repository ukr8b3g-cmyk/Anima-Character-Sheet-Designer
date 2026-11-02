from .catalog import DEFAULT, REVISION
from .state import compact, parse_state, fail, StateError
from .tagger_contracts import manual_text, profile as parse_profile, sha_text, hash_value
from .compiler import compile_views, MAX_SEED
from .layout import compute_layout

def runtime_max():
    try:
        from nodes import MAX_RESOLUTION
        return min(MAX_RESOLUTION,16384)
    except ImportError: return 16384

def generation_signature(records):
    return hash_value([{k:r[k] for k in ('view_id','width','height','seed','positive')} for r in records])

def input_source(prompt,profile=None):
    return dict(mode='image_tags' if profile else 'manual',prompt_sha256=sha_text(prompt),
        profile_hash=profile['profile_hash'] if profile else None,image_hash=profile['image_hash'] if profile else None,
        tagger_model_id=profile['model_id'] if profile else None,tagger_model_sha256=profile['model_sha256'] if profile else None)

class AnimaCharacterSheetDesigner:
    CATEGORY='Anima/Character Sheet'
    FUNCTION='compile'
    RETURN_TYPES=('STRING','INT','INT','INT','STRING','STRING')
    RETURN_NAMES=('positive','width','height','seed','sheet_plan','view_records')
    OUTPUT_IS_LIST=(True,True,True,True,False,True)
    DESCRIPTION='Compile independent views from a prompt, optionally scoped by Anima Image Tagger. Connect both prompt and profile_json for image tags.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'state_json':('STRING',{'default':compact(DEFAULT),'multiline':True,'dynamicPrompts':False}),
                            'base_seed':('INT',{'default':42,'min':0,'max':MAX_SEED})},
                'optional':{'prompt':('STRING',{'forceInput':True}),'profile_json':('STRING',{'forceInput':True})},
                'hidden':{'workflow_prompt':'PROMPT','unique_id':'UNIQUE_ID'}}

    @classmethod
    def VALIDATE_INPUTS(cls,state_json,base_seed=42,prompt=None,profile_json=None):
        try:
            state=parse_state(state_json,runtime_max()); compile_views(state,base_seed)
            if isinstance(prompt,str):
                manual_text(prompt)
                if profile_json: parse_profile(profile_json,prompt)
            return True
        except StateError as exc: return str(exc)

    def compile(self,state_json,base_seed=42,prompt=None,profile_json='',workflow_prompt=None,unique_id=None,**legacy):
        old=(workflow_prompt or {}).get(str(unique_id),{}).get('inputs',{})
        if legacy.get('use_image') or legacy.get('character_image') is not None or old.get('use_image') not in (None,False) or any(k in old for k in ('character_image','reference_mask')):
            fail('E_LEGACY_REFERENCE_REMOVED','AnimaCharacterSheetDesigner','Use the new Text-or-Image workflow with Anima Image Tagger. Ref Adapter inputs are no longer supported.')
        state=parse_state(state_json,runtime_max()); manual_text(prompt)
        p=parse_profile(profile_json,prompt) if profile_json else None
        if p:
            from .tagger_profile import scoped_tags
            for view in state['views']:
                if not scoped_tags(p,view,state):
                    print(f'[Anima Designer] W_UNDERDESCRIBED_VIEW: {view}: no scoped appearance tags; view and explicit part instructions remain active.',flush=True)
        records=compile_views(state,base_seed,prompt,p)
        layout=compute_layout(state,runtime_max())
        plan=dict(schema_version=2,kind='anima_character_sheet_plan',compiler_revision=REVISION,canvas=layout['canvas'],background=state['background'],input_source=input_source(prompt,p),generation_signature=generation_signature(records),views=[dict(view_id=v['id'],bounds=v['bbox_px']) for v in layout['panels']])
        plan['plan_hash']=hash_value(plan)
        for record in records: record.update(schema_version=2,sheet_plan_hash=plan['plan_hash'],record_kind='declared_generation_plan')
        return (*([r[k] for r in records] for k in ('positive','width','height','seed')),compact(plan),[compact(r) for r in records])
