import hashlib
import re
from .catalog import CONTRACT as C, VIEWS, PARTS, REVISION
from .state import parse_state, state_hash, fail
from .layout import compute_layout

MAX_SEED = (1 << 53) - 1

def format_positive(parts):
    return ', '.join(chunk.strip() for part in parts for chunk in re.split(r'[,\r\n]+', part) if chunk.strip())

def default_view_prompt(view_id):
    return C['view_prompt_defaults'][view_id]

def view_seed(base_seed, view_id, offset=0):
    if type(base_seed) is not int or not 0 <= base_seed <= MAX_SEED:
        fail('E_SEED_RANGE', 'base_seed')
    return int.from_bytes(hashlib.sha256(f'anima-sheet-seed-v1\n{base_seed}\n{view_id}\n{offset}'.encode()).digest()[:8], 'big') & MAX_SEED

def compile_views(state, base_seed=42, prompt='', profile=None):
    result = []
    for v in state['views']:
        definition = C['views'][v]
        kind = definition['kind']
        source = prompt
        if profile is not None:
            from .tagger_profile import scoped_tags
            source = scoped_tags(profile,v,state)
        positive = []
        scoped_source = bool(source.strip()) and kind != 'body'
        if scoped_source:
            # Use the source as appearance context, then state this view's framing.
            positive.append(f'({source}:0.5)')
        if kind in ('portrait', 'body'):
            positive.append({'woman':'1girl, solo', 'man':'1boy, solo', 'person':'one person, solo',
                             'nonhuman':'one character, solo', 'unspecified':'solo'}[state['subject_kind']])
        base_prompt = state['view_prompts'].get(v, default_view_prompt(v))
        if v == 'feet' and state['appearance']['footwear_state'] == 'unshod' and v not in state['view_prompts']:
            base_prompt = 'feet, close-up, one pair of feet, complete feet, referenced socks or tights'
        description = 'Design description: ' + source if source.strip() else ''
        positive.extend([base_prompt, C['backgrounds'][state['background']]])
        if not scoped_source:
            if description:
                positive.append(description)
            elif profile is None and kind in ('portrait', 'body'):
                positive.append('Wearing the same outfit as the reference.')
        for part in PARTS:
            if v in C['part_visibility'][part] and state['part_prompts'].get(part):
                positive.append(state['part_prompts'][part])
        a = state['appearance']
        if v in C['setting_visibility']['clothing_type']:
            if a['clothing_type'] != 'auto':
                positive.append({'pants':'trousers', 'skirt_robe':'skirt or robe'}[a['clothing_type']])
        if v in C['setting_visibility']['hand_state']:
            if a['hand_state'] == 'gloved': positive.append('gloves')
            elif a['hand_state'] == 'bare': positive.append('bare hands')
        if v in C['setting_visibility']['footwear_state']:
            if a['footwear_state'] == 'shod' and v != 'feet': positive.append('footwear')
            elif a['footwear_state'] == 'unshod':
                positive.append('Feet with the referenced socks or tights and footwear removed.')
        if C['styles'][state['style']]: positive.append(C['styles'][state['style']])
        sizes = C['render_sizes'][state['render_profile']]
        width, height = sizes['footwear'] if v == 'feet' and a['footwear_state'] != 'unshod' else sizes[kind]
        result.append(dict(view_id=v, width=width, height=height,
                           seed=view_seed(base_seed,v,state['view_seed_offsets'].get(v,0)),
                           positive=format_positive(positive)))
    return result

def preview(raw, runtime_max_resolution=16384):
    state = parse_state(raw, runtime_max_resolution)
    layout = compute_layout(state, runtime_max_resolution)
    records = compile_views(state)
    warnings = []
    if any(C['views'][v]['quality_status'] != 'standard_target' for v in state['views']):
        warnings.append(dict(code='experimental_views', path='views', details='Viewpoint and garment separation require GPU quality validation.'))
    if state['style'] in ('photo','realistic_painting'):
        warnings.append(dict(code='experimental_style',path='style',details='Anima is primarily an illustration model.'))
    w,h = layout['canvas']
    return dict(schema_version=1, compiler_revision=REVISION, input_hash=state_hash(state),
                canonical_state=state, ready=True, width=w, height=h, layout_plan=layout,
                prompt='\n\n'.join(r['view_id'] + '\n' + r['positive'] for r in records),
                resolved_format='independent_views',
                default_view_prompts={v:default_view_prompt(v) for v in VIEWS},
                view_prompts=records, warnings=warnings, blocking_errors=[], token_status='not_measured')
