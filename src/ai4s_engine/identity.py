"""Resolve agreement-3 identity from the actual, read-only model deployment."""
import hashlib
import json
from pathlib import Path

IDENTITY_FIELDS = ('model_id', 'release', 'source_commit', 'model_name', 'weights_family', 'weights_sha256')


def identity_digest(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def resolve_identity(model_root, model_name):
    release = (Path(model_root) / 'current').resolve(strict=True)
    manifest = json.loads((release / 'manifest.json').read_text())
    relative = f'vanilla_model_weights/{model_name}.pt'
    expected = manifest['weights_sha256'][relative]
    weights = release / 'source' / 'ProteinMPNN' / relative
    with weights.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    if expected != actual:
        raise ValueError('deployed weights SHA-256 differs from manifest')
    source = manifest['source_commit']
    identity = dict(model_id='proteinmpnn', release=release.name, source_commit=source,
                    model_name=model_name, weights_family='vanilla', weights_sha256=actual)
    if any(not isinstance(value, str) or not value for value in identity.values()):
        raise ValueError('model identity contains unresolved fields')
    return identity
