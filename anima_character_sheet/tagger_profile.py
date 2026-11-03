"""Deterministic appearance filtering. Model scores never become prompt weights."""
import re
from .tagger_contracts import resource, sha_text, hash_value, canonical
from .state import fail

POLICY=resource('contracts/appearance_policy.v1.json')
GROUPS=POLICY['group_order']
ALLOW={tag:group for group in GROUPS for tag in POLICY['exact_allow'][group]}
EXCLUDE=set(POLICY['exact_exclude'])

def literal(tag):
    tag=tag.lower().strip()
    if not re.fullmatch(r'score_\d+(?:_up)?',tag): tag=tag.replace('_',' ')
    return re.sub(r'([\\()\[\]:])',r'\\\1',tag)

def filter_tags(tags, cfg, model):
    thresholds={k:cfg['thresholds'].get(k) if cfg['thresholds'].get(k) is not None else v for k,v in model['thresholds'].items()}
    above=[]
    for i,tag in enumerate(tags):
        category=model['categories'].get(str(tag.get('category',0)))
        if category is None: fail('E_TAG_CATEGORY','selected_tags.csv')
        if tag['score']>=thresholds[category]: above.append(dict(tag,index=tag.get('index',i),category_name=category))
    above.sort(key=lambda t:(-t['score'],t['index']))
    general={t['name'] for t in above if t['category_name']=='general'}
    multi=bool(general & set(POLICY['multiple_subject_tags'])) or len(general & {'1girl','1boy','1other'})>1
    if multi and cfg['multi_subject_policy']=='block': fail('E_MULTIPLE_SUBJECTS','image','Use a single-character image, or explicitly allow multiple-subject tags.')
    excluded=[]; review=[]; kept=[]; identities={'character':[],'copyright':[]}; seen=set()
    omit={t.lower().strip().replace(' ','_') for t in cfg['exclude_tags']}
    for t in above:
        name=t['name']; category=t['category_name']; reason=None
        if name in seen: reason='duplicate'
        elif name in omit: reason='user_excluded'
        elif category in identities and cfg['include_'+category]:
            if len(identities[category])<8: identities[category].append(name); seen.add(name); continue
            reason='identity_limit'
        elif category!='general': reason='category_disabled'
        elif name in EXCLUDE or name in POLICY['multiple_subject_tags']: reason='non_appearance'
        elif name not in ALLOW:
            review.append(dict(name=name,reason='unknown_tag',score=t['score'])); continue
        elif len(kept)>=cfg['max_tags']: reason='max_tags'
        else: kept.append(t); seen.add(name); continue
        excluded.append(dict(name=name,reason=reason,score=t['score']))
    groups={g:[] for g in GROUPS}
    for t in kept: groups[ALLOW[t['name']]].append(t['name'])
    additions={}
    for g in GROUPS:
        for tag in cfg['scope_additions'].get(g,[]):
            name=tag.strip().lower().replace(' ','_')
            if not name or name in seen: continue
            additions.setdefault(g,[]).append(name); seen.add(name)
    return dict(groups=groups,identity_labels=identities,user_additions=additions,excluded=excluded,review=review,multiple_subjects=multi)

def build_profile(tags,cfg,model,image_hash):
    f=filter_tags(tags,cfg,model)
    appearance=[tag for g in GROUPS for tag in f['groups'][g]+f['user_additions'].get(g,[])]
    if not appearance: fail('E_APPEARANCE_EMPTY','image','No accepted appearance tags. Review tags and add necessary features in Advanced.')
    all_tags=appearance+f['identity_labels']['character']+f['identity_labels']['copyright']
    prompt=', '.join(literal(t) for t in all_tags)
    p=dict(schema_version=1,kind='anima_appearance_profile',source_mode='image_tags',image_hash=image_hash,model_id=model['id'],model_sha256=model['sha256'],preprocess_revision=model['preprocess_revision'],filter_revision=POLICY['revision'],prompt_sha256=sha_text(prompt),groups=f['groups'],identity_labels=f['identity_labels'],user_additions=f['user_additions'],review_count=len(f['review']))
    p['profile_hash']=hash_value(p)
    return prompt,p,f

def scoped_tags(p,view,state):
    selected=resource('contracts/view_scope.v1.json')['view_groups'][view]
    result=[]
    # Explicit appearance settings win over inferred machine tags. Socks/tights remain.
    shoe_tags={t for t in POLICY['exact_allow']['feet'] if any(t==x or t.endswith('_'+x) for x in ('shoes','boots','footwear','sandals','sneakers','heels','loafers','slippers','geta','zouri','mary_janes'))}
    glove_tags={t for t in POLICY['exact_allow']['hands'] if t in ('gloves','mittens') or t.endswith('_gloves')}
    a=state['appearance']
    lower_types={'pants':('skirt',),'skirt_robe':('pants','trousers','shorts')}.get(a['clothing_type'],())
    for g in selected:
        auto=p['groups'][g]
        if g=='lower_outfit': auto=[t for t in auto if not any(t==kind or t.endswith('_'+kind) for kind in lower_types)]
        if g=='subject' and state['subject_kind']!='unspecified': auto=[]
        if state['appearance']['footwear_state']=='unshod': auto=[t for t in auto if t not in shoe_tags]
        elif a['footwear_state']=='shod': auto=[t for t in auto if t!='barefoot']
        if state['appearance']['hand_state']=='bare': auto=[t for t in auto if t not in glove_tags]
        elif a['hand_state']=='gloved': auto=[t for t in auto if t!='bare_hands']
        result.extend(auto+p['user_additions'].get(g,[]))
    if view.startswith(('face_','body_')):
        result.extend(p['identity_labels']['character']+p['identity_labels']['copyright'])
    return ', '.join(literal(t) for t in dict.fromkeys(result))
