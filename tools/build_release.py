"""Build deterministic install/workflow ZIPs without model weights or local logs."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0'
FOLDER = 'Anima-Character-Sheet-Designer'
DEST = ROOT / 'dist'
DEST.mkdir(exist_ok=True)
assert re.search(r'version\s*=\s*"1\.0"', (ROOT / 'pyproject.toml').read_text('utf8'))
assert "__version__ = '1.0'" in (ROOT / '__init__.py').read_text('utf8')
assert "'v1.0'" in (ROOT / 'web/ui.js').read_text('utf8')
files = [ROOT / p for p in ('__init__.py', 'pyproject.toml', 'requirements.txt', 'README.md',
                          'README.ja.md', 'LICENSE', 'NOTICE.md', 'CHANGELOG.md')]
for directory in ('anima_character_sheet', 'web', 'schemas', 'locales', 'docs/images', 'examples'):
    files.extend(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
files.extend(ROOT / 'contracts' / name for name in (
    'appearance_policy.v1.json', 'default_state.json', 'default_tagger_config.json',
    'models.v1.json', 'seed_golden_vectors.json', 'view_contract.v1.json', 'view_scope.v1.json'))
files = sorted(set(files), key=lambda p: p.relative_to(ROOT).as_posix())
assert all(p.exists() for p in files)
assert len(list((ROOT / 'examples').glob('*.json'))) == 1
assert not any(p.suffix in ('.onnx', '.safetensors', '.log') for p in files)

def archive(path, entries):
    # Stored entries avoid platform/zlib differences; the bitmap assets are
    # already compressed. ZIP bytes therefore match Windows and CI builds.
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as output:
        for source, name in entries:
            info = zipfile.ZipInfo(name, (2026, 11, 3, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            output.writestr(info, source.read_bytes())
    with zipfile.ZipFile(path) as result:
        assert result.testzip() is None
        for source, name in entries:
            assert result.read(name) == source.read_bytes()

package = DEST / f'{FOLDER}-v{VERSION}.zip'
workflow = DEST / f'{FOLDER}-Workflow-v{VERSION}.zip'
archive(package, [(p, FOLDER + '/' + p.relative_to(ROOT).as_posix()) for p in files])
archive(workflow, [(p, p.name) for p in sorted((ROOT / 'examples').iterdir(), key=lambda p: p.name) if p.is_file()])
summary = [{'name': p.name, 'bytes': p.stat().st_size,
            'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (package, workflow)]
(DEST / 'SHA256SUMS.txt').write_text(''.join(f"{p['sha256']}  {p['name']}\n" for p in summary), 'utf8')
print(json.dumps({'version': VERSION, 'install_files': len(files), 'assets': summary}, indent=2))
