"""Small JSON boundary shared by the tagger and scoped compiler (no ML imports)."""
import hashlib
import json
from functools import lru_cache
from .catalog import ROOT
from .state import fail, pairs

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def hash_value(value):
    return sha_text(canonical(value))

@lru_cache(maxsize=16)
def resource(name):
    return json.loads((ROOT/name).read_text('utf-8'))

def unicode_check(value):
    if isinstance(value, str):
        try: value.encode('utf-8')
        except UnicodeEncodeError: fail('E_UNICODE', 'tagger')
    elif isinstance(value, dict):
        for k,v in value.items(): unicode_check(k); unicode_check(v)
    elif isinstance(value, list):
        for v in value: unicode_check(v)

def load_json(raw, limit=65536):
    if not isinstance(raw, str): fail('E_TYPE', 'tagger_json')
    unicode_check(raw)
    if len(raw.encode('utf-8')) > limit: fail('E_TEXT_LIMIT', 'tagger_json')
    try:
        result=json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _:fail('E_NONFINITE', 'tagger_json'))
        unicode_check(result)
        # Reject overflowing JSON floats as well as explicit Infinity/NaN.
        canonical(result)
        return result
    except (json.JSONDecodeError, RecursionError, OverflowError): fail('E_JSON_SYNTAX', 'tagger_json')
    except ValueError as exc:
        from .state import StateError
        if isinstance(exc, StateError): raise
        fail('E_NONFINITE', 'tagger_json')

def validate_schema(value, name):
    code='E_PROFILE_SCHEMA' if name.startswith('appearance_profile') else 'E_TAGGER_SCHEMA'
    if isinstance(value,dict) and type(value.get('schema_version')) is not int: fail(code,'schema_version','Expected an integer version.')
    from jsonschema import Draft202012Validator, validators
    types=Draft202012Validator.TYPE_CHECKER.redefine('integer', lambda _,v:type(v) is int)
    validator=validators.extend(Draft202012Validator, type_checker=types)
    error=next(validator(resource('schemas/'+name)).iter_errors(value),None)
    if error: fail(code, '.'.join(str(p) for p in error.path), error.message[:200])
    return value

def config(raw):
    return validate_schema(load_json(raw),'tagger_config.v1.schema.json')

def manual_text(prompt):
    if not isinstance(prompt,str) or not prompt.strip(): fail('E_PROMPT_EMPTY','manual_prompt')
    unicode_check(prompt)
    if len(prompt)>4000 or len(prompt.encode('utf-8'))>16000: fail('E_TEXT_LIMIT','manual_prompt')
    return prompt

def model_spec(model_id):
    for model in resource('contracts/models.v1.json')['models']:
        if model['id']==model_id: return model
    fail('E_TAGGER_MODEL','model_id')

def profile(raw, prompt):
    p=validate_schema(load_json(raw,262144),'appearance_profile.v1.schema.json')
    if hash_value({k:v for k,v in p.items() if k!='profile_hash'})!=p['profile_hash']: fail('E_PROFILE_HASH','profile_json')
    if p['prompt_sha256']!=sha_text(prompt): fail('E_PROFILE_PROMPT_MISMATCH','profile_json')
    m=model_spec(p['model_id'])
    if p['model_sha256']!=m['sha256'] or p['preprocess_revision']!=m['preprocess_revision']: fail('E_PROFILE_MODEL','profile_json')
    policy=resource('contracts/appearance_policy.v1.json')
    if p['filter_revision']!=policy['revision']: fail('E_PROFILE_FILTER','profile_json')
    for group,tags in p['groups'].items():
        if any(t not in policy['exact_allow'][group] for t in tags): fail('E_PROFILE_GROUP',group)
    return p
