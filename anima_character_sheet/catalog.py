import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / 'contracts/view_contract.v1.json').read_text('utf-8'))
DEFAULT = json.loads((ROOT / 'contracts/default_state.json').read_text('utf-8'))
SCHEMA = json.loads((ROOT / 'schemas/state.v1.schema.json').read_text('utf-8'))
VIEWS = CONTRACT['view_order']
PARTS = CONTRACT['part_order']
REVISION = CONTRACT['contract_version']
