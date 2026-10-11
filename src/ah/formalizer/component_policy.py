"""Release policy and whole-variant morphology shared by component stages."""
from dataclasses import asdict

def policy(release):
    return release.entries('ProposalPolicy')[0].get('composition')


def _features(v):
    return {k: getattr(v, k) for k in ('gender', 'number', 'person') if getattr(v, k)}


def compatible(a, b):
    return all(not a.get(k) or not b.get(k) or a[k] == b[k]
               for k in ('number', 'gender', 'person'))


def _morph(v):
    raw = asdict(v)
    raw['cases'], raw['features'] = sorted(v.cases), sorted(v.features)
    return raw


