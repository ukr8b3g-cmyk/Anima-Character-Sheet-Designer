import hashlib
import json
from .catalog import DEFAULT, SCHEMA, VIEWS, PARTS

class StateError(ValueError):
    def __init__(self, code, path='state_json', details=''):
        self.code, self.path, self.details = code, path, details
        super().__init__(f'{code}: {path} {details}')

def fail(code, path='state_json', details=''):
    raise StateError(code, path, details)

def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            fail('E_DUPLICATE_KEY', key)
        result[key] = value
    return result

def strict_load(raw):
    if not isinstance(raw, str):
        fail('E_TYPE')
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_float=lambda _: fail('E_TYPE'),
                          parse_constant=lambda _: fail('E_TYPE'))
    except (json.JSONDecodeError, RecursionError):
        fail('E_JSON_SYNTAX')

def validate(value, schema, path):
    kind = schema.get('type')
    if kind == 'object':
        if type(value) is not dict:
            fail('E_TYPE', path)
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - value.keys():
            fail('E_KEYS', path)
        for k, v in value.items():
            rule = props.get(k, schema.get('additionalProperties', {}))
            if rule is False:
                fail('E_KEYS', path + '.' + k)
            validate(v, rule if isinstance(rule, dict) else {}, path + '.' + k)
    elif kind == 'array':
        if type(value) is not list:
            fail('E_TYPE', path)
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 1 << 30):
            fail('E_VIEW_SET', path)
        for v in value:
            validate(v, schema.get('items', {}), path)
        if schema.get('uniqueItems') and len(set(value)) != len(value):
            fail('E_VIEW_SET', path)
    elif kind == 'string':
        if type(value) is not str:
            fail('E_TYPE', path)
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            fail('E_UNICODE', path)
        if len(value) > schema.get('maxLength', 1 << 30):
            fail('E_TEXT_LIMIT', path)
    elif kind == 'integer':
        if type(value) is not int:
            fail('E_TYPE', path)
        if not schema.get('minimum', -1 << 100) <= value <= schema.get('maximum', 1 << 100):
            fail('E_SIZE_RANGE', path)
        if value % schema.get('multipleOf', 1):
            fail('E_SIZE_STEP', path)
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        fail('E_SCHEMA', path)
    if 'enum' in schema and value not in schema['enum']:
        fail('E_ENUM', path)

def parse_state(raw, runtime_max_resolution=16384):
    if not isinstance(raw, str):
        fail('E_TYPE')
    try:
        if len(raw.encode('utf-8')) > 65536:
            fail('E_STATE_SIZE')
    except UnicodeEncodeError:
        fail('E_UNICODE')
    s = strict_load(raw)
    s.pop('negative_extra', None)  # Discard the removed preview-only field from local saved workflows.
    s.pop('positive_common', None)  # Common quality tags now belong to the external prompt.
    s.setdefault('view_prompts', {})
    validate(s, SCHEMA, 'state_json')
    for k in ('body_height', 'manual_width', 'manual_height'):
        if s['size'][k] > min(16384, runtime_max_resolution):
            fail('E_SIZE_RANGE', 'size.' + k)
    if s['size']['mode'] == 'manual' and s['size']['manual_width'] * s['size']['manual_height'] > 16777216:
        fail('E_PIXEL_LIMIT', 'size')
    s = {k: s[k] for k in DEFAULT}
    s['views'] = [v for v in VIEWS if v in s['views']]
    s['part_prompts'] = {k: s['part_prompts'][k] for k in PARTS if s['part_prompts'].get(k, '').strip()}
    s['appearance'] = {k: s['appearance'][k] for k in DEFAULT['appearance']}
    s['size'] = {k: s['size'][k] for k in DEFAULT['size']}
    return s

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def state_hash(value):
    return hashlib.sha256(compact(value).encode('utf-8')).hexdigest()
