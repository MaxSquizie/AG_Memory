"""Ed25519 review verification against an externally managed key registry.

The signature binds content, reviewer, timestamp and key identity. A release
cannot authorize its own key. Signing requires a supplied reviewer private key;
this module never generates one or assigns a review identity.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime


def review_message(review):
    fields = ('algorithm', 'key_id', 'reviewer', 'timestamp', 'reviewed_sha256')
    if not isinstance(review, dict) or set(review) != set(fields) | {'signature'}:
        raise ValueError('invalid signed review fields')
    if any(not isinstance(review[k], str) or not review[k] for k in fields):
        raise ValueError('empty signed review field')
    if review['algorithm'] != 'Ed25519':
        raise ValueError('unsupported review signature algorithm')
    timestamp = datetime.fromisoformat(review['timestamp'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('review timestamp must include timezone')
    import re
    if not re.fullmatch(r'[0-9a-f]{64}', review['reviewed_sha256']):
        raise ValueError('invalid reviewed digest')
    return json.dumps({'purpose': 'AG_MEMORY_RESOURCE_REVIEW_V1',
                       **{k: review[k] for k in fields}},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def verify_review(review, trusted, sha256):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(trusted, dict) or set(trusted) != {'keys', 'reviews'}:
        raise ValueError('trusted registry requires keys and pinned reviews')
    if review.get('reviewed_sha256') != sha256 or trusted['reviews'].get(sha256) != review:
        raise ValueError('review is not pinned to this snapshot')
    key = trusted['keys'].get(review.get('key_id'))
    if (not isinstance(key, dict) or key.get('reviewer') != review.get('reviewer')
            or key.get('revoked', False) is not False):
        raise ValueError('review key is absent, revoked or belongs to another reviewer')
    timestamp=datetime.fromisoformat(review['timestamp'].replace('Z','+00:00'))
    if timestamp.tzinfo is None:raise ValueError('review timestamp must include timezone')
    # Optional validity boundaries are external trust policy, never self-issued
    # by the release. No wall-clock input changes historical replay decisions.
    for field,direction in (('valid_from','before'),('valid_until','after')):
        if field not in key:continue
        bound=datetime.fromisoformat(key[field].replace('Z','+00:00'))
        if bound.tzinfo is None:raise ValueError('trust validity boundary must include timezone')
        if direction=='before' and timestamp<bound or direction=='after' and timestamp>bound:
            raise ValueError('review timestamp outside trusted key validity')
    public = base64.b64decode(key['public_key_b64'], validate=True)
    signature = base64.b64decode(review['signature'], validate=True)
    if len(public) != 32 or len(signature) != 64:
        raise ValueError('invalid Ed25519 key/signature size')
    Ed25519PublicKey.from_public_bytes(public).verify(signature, review_message(review))


def sign_review(sha256, *, reviewer, timestamp, key_id, private_key_pem):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('review key must be Ed25519')
    review = {'algorithm': 'Ed25519', 'key_id': key_id, 'reviewer': reviewer,
              'timestamp': timestamp, 'reviewed_sha256': sha256, 'signature': ''}
    review['signature'] = base64.b64encode(key.sign(review_message(review))).decode('ascii')
    return review
