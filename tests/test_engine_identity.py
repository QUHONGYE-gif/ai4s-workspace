"""Independent agreement-3 vector and deployed-weight integrity checks."""
import hashlib
import json
from pathlib import Path

import pytest

from ai4s_engine.identity import identity_digest, resolve_identity


def test_published_identity_vector():
    identity = dict(model_id='proteinmpnn', model_name='v_48_020',
                    release='8907e667-py312-torch260cu124',
                    source_commit='8907e6671bfbfc92303b5f79c4b5e6ce47cdef57', weights_family='vanilla',
                    weights_sha256='c9cb4a671d79604111231f8dbfc7c590e06f1197453b7a6854ac6661a642f5bd')
    assert identity_digest(identity) == '865635b5e489a115b5572f1ad72384f80517ce57d30100d673d38a7c4b5d36a0'
    assert identity_digest(dict(reversed(list(identity.items())))) == identity_digest(identity)


def test_weight_content_is_checked_against_manifest(tmp_path):
    release = tmp_path / 'releases' / 'test-release'
    weights = release / 'source/ProteinMPNN/vanilla_model_weights/v_48_020.pt'
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b'known weight bytes')
    expected = hashlib.sha256(b'known weight bytes').hexdigest()
    (release / 'manifest.json').write_text(json.dumps({'source_commit': 'abc', 'weights_sha256': {'vanilla_model_weights/v_48_020.pt': expected}}))
    (tmp_path / 'current').symlink_to(release)
    assert resolve_identity(tmp_path, 'v_48_020')['weights_sha256'] == expected
    weights.write_bytes(b'changed content at same path')
    with pytest.raises(ValueError, match='differs from manifest'):
        resolve_identity(tmp_path, 'v_48_020')
