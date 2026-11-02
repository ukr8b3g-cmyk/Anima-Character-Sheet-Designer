import torch
import torch.nn.functional as F
from .catalog import VIEWS, REVISION
from .state import strict_load, compact, digest, fail
from .node import runtime_max, generation_signature
from .image_utils import check_image
from .tagger_contracts import hash_value, validate_schema, model_spec

def validate_plan(plan):
    if type(plan) is not dict or type(plan.get('schema_version')) is not int: fail('E_VIEW_RECORD','sheet_plan')
    version=plan['schema_version']
    if version==2:
        validate_schema(plan,'sheet_plan.v2.schema.json')
        source=plan['input_source']
        if source['mode']=='image_tags' and source['tagger_model_sha256']!=model_spec(source['tagger_model_id'])['sha256']: fail('E_PROFILE_MODEL')
    elif version==1:
        expected={'schema_version','kind','compiler_revision','canvas','background','reference_hash','views','plan_hash'}
        if set(plan)!=expected or plan['kind']!='anima_character_sheet_plan' or plan['compiler_revision'] not in ('anima-sheet-1.0.1','anima-sheet-1.0.2','anima-sheet-1.0.3'): fail('E_VIEW_RECORD','sheet_plan')
        if not isinstance(plan['reference_hash'],str) or len(plan['reference_hash'])!=64: fail('E_VIEW_RECORD','reference_hash')
    else: fail('E_VIEW_RECORD','schema_version')
    hasher=hash_value if version==2 else digest
    if plan['plan_hash'] != hasher({k:v for k,v in plan.items() if k != 'plan_hash'}): fail('E_PLAN_HASH')
    canvas = plan['canvas']
    if type(canvas) is not list or len(canvas) != 2 or any(type(n) is not int or not 256 <= n <= runtime_max() or n % 16 for n in canvas): fail('E_SIZE', 'canvas')
    w,h = canvas
    if w*h > 16777216: fail('E_PIXEL_LIMIT', 'canvas')
    if plan['background'] not in ('white','light_gray'): fail('E_VIEW_RECORD', 'background')
    views = plan['views']
    if type(views) is not list or not 1 <= len(views) <= 13: fail('E_VIEW_SET')
    seen, boxes = set(), []
    for v in views:
        if type(v) is not dict or set(v) != {'view_id','bounds'}: fail('E_VIEW_RECORD')
        if v['view_id'] not in VIEWS or v['view_id'] in seen: fail('E_VIEW_SET')
        seen.add(v['view_id'])
        b = v['bounds']
        if type(b) is not list or len(b) != 4 or any(type(n) is not int for n in b): fail('E_BBOX')
        x0,y0,x1,y1 = b
        if not 0 <= x0 < x1 <= w or not 0 <= y0 < y1 <= h: fail('E_BBOX')
        if any(max(x0,c[0]) < min(x1,c[2]) and max(y0,c[1]) < min(y1,c[3]) for c in boxes): fail('E_BBOX')
        boxes.append(b)
    if [v['view_id'] for v in views] != [v for v in VIEWS if v in seen]: fail('E_VIEW_SET')

class AnimaCharacterSheetAssemble:
    CATEGORY = 'Anima/Character Sheet'
    FUNCTION = 'assemble'
    INPUT_IS_LIST = True
    RETURN_TYPES = ('IMAGE','STRING')
    RETURN_NAMES = ('sheet','assembly_info')
    DESCRIPTION = 'Assemble independent images in their planned regions. Missing, extra or mismatched images stop with an error. Does not classify viewpoints or remove backgrounds.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'images':('IMAGE',),'view_records':('STRING',),'sheet_plan':('STRING',)}}

    def assemble(self, images, view_records, sheet_plan):
        if len(sheet_plan) != 1: fail('E_LIST_LENGTH','sheet_plan')
        plan = strict_load(sheet_plan[0]); validate_plan(plan)
        if len(images) != len(plan['views']) or len(view_records) != len(images): fail('E_LIST_LENGTH')
        records = []
        expected = {'schema_version','view_id','sheet_plan_hash','width','height','seed','positive','record_kind'}
        for image,raw,view in zip(images,view_records,plan['views'],strict=True):
            r = strict_load(raw)
            if type(r) is not dict or set(r) != expected or r['view_id'] != view['view_id'] or r['sheet_plan_hash'] != plan['plan_hash'] or r['record_kind'] != 'declared_generation_plan': fail('E_VIEW_RECORD')
            if type(r['schema_version']) is not int or r['schema_version'] != plan['schema_version'] or any(type(r[k]) is not int for k in ('width','height','seed')) or not 0 <= r['seed'] < 1 << 53 or type(r['positive']) is not str: fail('E_VIEW_RECORD')
            check_image(image, r['view_id'])
            if list(image.shape[1:3]) != [r['height'],r['width']]: fail('E_IMAGE_RECORD_SIZE',r['view_id'])
            records.append(r)
        if plan['schema_version']==2 and generation_signature(records)!=plan['generation_signature']: fail('E_GENERATION_SIGNATURE')
        w,h = plan['canvas']; bg = 1.0 if plan['background'] == 'white' else 0.94
        sheet = torch.full((1,h,w,3),bg,dtype=torch.float32,device='cpu')
        info = []
        for image,r,v in zip(images,records,plan['views'],strict=True):
            x0,y0,x1,y1 = v['bounds']; iw,ih = r['width'],r['height']
            scale = min((x1-x0)/iw,(y1-y0)/ih)
            rw,rh = max(1,round(iw*scale)),max(1,round(ih*scale))
            pixels = image.detach().to(device='cpu',dtype=torch.float32)
            if pixels.shape[-1] == 4: pixels = pixels[...,:3]*pixels[...,3:4]+bg*(1-pixels[...,3:4])
            resized = F.interpolate(pixels.permute(0,3,1,2),size=(rh,rw),mode='bilinear',align_corners=False,antialias=True).permute(0,2,3,1)
            x,y = x0+(x1-x0-rw)//2,y0+(y1-y0-rh)//2
            sheet[:,y:y+rh,x:x+rw] = resized.clamp(0,1)
            info.append(dict(**r,panel_bounds=v['bounds'],image_bounds=[x,y,x+rw,y+rh],source_size=[iw,ih]))
        return sheet, compact(dict(method='assembled_independent_views',canvas=plan['canvas'],plan_hash=plan['plan_hash'],views=info,
                                  limitation='Records describe declared inputs, not observed sampler settings. Image content, identity and viewpoint are not verified.'))
