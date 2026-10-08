"""Bounded textual Rule DSL v1 compiler into the existing SyntaxRules AST.

Captures and Emit payloads are JSON objects, not Python expressions. Predicates
retain three-valued AST semantics; compilation never runs a resource callback.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re


class RuleDslError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledRules:
    rules: tuple[dict, ...]
    dependency_versions: dict[str, str]


class Parser:
    def __init__(self, text):
        if not isinstance(text, str) or len(text) > 262144:
            raise RuleDslError('DSL_SOURCE_LIMIT')
        self.text, self.pos = text, 0
        self.decoder = json.JSONDecoder()

    def ws(self):
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text[self.pos] == '#':
                end = self.text.find('\n', self.pos)
                self.pos = len(self.text) if end < 0 else end + 1
            else:
                break

    def take(self, token, optional=False):
        self.ws()
        end = self.pos + len(token)
        if (self.text.startswith(token, self.pos)
                and (not token[-1].isalnum() or end == len(self.text)
                     or not (self.text[end].isalnum() or self.text[end] == '_'))):
            self.pos = end
            return True
        if optional:
            return False
        raise RuleDslError(f'expected {token!r} at {self.pos}')

    def ident(self):
        self.ws()
        m = re.match(r'[A-Za-z_][A-Za-z_0-9.-]*', self.text[self.pos:])
        if not m:
            raise RuleDslError(f'identifier expected at {self.pos}')
        self.pos += len(m[0])
        return m[0]

    def value(self):
        self.ws()
        try:
            value, end = self.decoder.raw_decode(self.text, self.pos)
        except ValueError as exc:
            raise RuleDslError(f'JSON value expected at {self.pos}') from exc
        self.pos = end
        # Reject non-finite JSON extensions accepted by Python's decoder.
        json.dumps(value, allow_nan=False)
        return value

    def expr(self, depth=0):
        if depth > 16:
            raise RuleDslError('DSL_DEPTH_LIMIT')
        def conjunction():
            xs = [self.check(depth + 1)]
            while self.take('AND', True):
                xs.append(self.check(depth + 1))
            return xs[0] if len(xs) == 1 else {'op': 'AND', 'args': xs}
        xs = [conjunction()]
        while self.take('OR', True):
            xs.append(conjunction())
        return xs[0] if len(xs) == 1 else {'op': 'OR', 'args': xs}

    def check(self, depth):
        if self.take('NOT', True):
            self.take('('); arg = self.expr(depth); self.take(')')
            return {'op': 'NOT', 'arg': arg}
        if self.take('(', True):
            result = self.expr(depth); self.take(')'); return result
        name = self.ident()
        if name in {'AGREE', 'WINDOW_HAS', 'LOOKUP'}:
            self.take('(')
            if name == 'AGREE':
                a = self.ident(); self.take(','); b = self.ident(); self.take(')')
                return {'op': 'agreement', 'left': a, 'right': b}
            if name == 'WINDOW_HAS':
                source = self.ident(); self.take(','); expr = self.expr(depth); self.take(')')
                return {'op': 'window_has', 'source': source, 'expr': expr}
            resource = self.ident(); self.take(','); key = self.value(); self.take(')')
            return {'op': 'schema_lookup', 'resource': resource, 'key': key}
        if self.take('=', True):
            return {'op': 'feature_eq', 'field': name, 'value': self.value()}
        if self.take('IN', True):
            self.take('{'); values = [self.value()]
            while self.take(',', True): values.append(self.value())
            self.take('}')
            return {'op': 'feature_in', 'field': name, 'values': values}
        relation = self.ident()
        if relation not in {'BEFORE', 'AFTER', 'OVERLAPS', 'CONTAINS', 'ADJACENT'}:
            raise RuleDslError('unknown span relation')
        return {'op': 'span_relation', 'left': name, 'right': self.ident(), 'relation': relation}

    def rules(self):
        rules, dependencies = [], {}
        while True:
            self.ws()
            if self.pos == len(self.text): break
            if len(rules) >= 4096: raise RuleDslError('DSL_RULE_LIMIT')
            self.take('rule'); rid = self.ident(); self.take(':')
            self.ws()
            m = re.match(r'[A-Za-z_0-9.-]+', self.text[self.pos:])
            if not m: raise RuleDslError('rule version required')
            version = m[0]; self.pos += len(version); self.take('{')
            fields = {}
            while True:
                key = self.ident()
                if key in fields: raise RuleDslError('duplicate rule field: ' + key)
                if key == 'reads':
                    self.take('['); reads = {}
                    if not self.take(']', True):
                        while True:
                            resource = self.ident(); self.take(':')
                            if self.ident() != 'entries': raise RuleDslError('only declared entries lookup is supported')
                            self.take('@'); self.ws()
                            v = re.match(r'[A-Za-z_0-9.-]+', self.text[self.pos:])
                            if not v or resource in reads: raise RuleDslError('invalid duplicate read')
                            self.pos += len(v[0]); reads[resource] = v[0]
                            if self.take(']', True): break
                            self.take(',')
                    fields[key] = reads
                elif key == 'when':
                    fields[key] = self.expr()
                elif key == 'emit':
                    self.take('Emit'); kind = self.ident(); payload = self.value()
                    fields[key] = (kind, payload)
                else:
                    if key not in {'stage', 'captures', 'priority', 'min_evidence', 'coverage_tag', 'window', 'distinct', 'constraints', 'cost'}:
                        raise RuleDslError('unknown rule field: ' + key)
                    self.take('=')
                    fields[key] = self.ident() if key in {'stage', 'cost'} else self.value()
                if self.take('}', True): break
                self.take(',')
            required = {'stage', 'reads', 'captures', 'when', 'emit', 'priority', 'min_evidence', 'coverage_tag'}
            if not required <= set(fields): raise RuleDslError('incomplete rule fields')
            if fields.get('cost', 'BOUNDED_JOIN') not in {'CONSTANT', 'LINEAR', 'BOUNDED_JOIN'}:
                raise RuleDslError('unknown bounded cost class')
            for resource, v in fields['reads'].items():
                if resource in dependencies and dependencies[resource] != v:
                    raise RuleDslError('conflicting read version')
                dependencies[resource] = v
            kind, payload = fields['emit']
            rules.append({'rule_id': rid + '@' + version, 'stage': fields['stage'],
                'input_feature_pattern': {'captures': fields['captures'], 'where': fields['when'],
                    'window': fields.get('window', 'SENTENCE'), 'distinct': fields.get('distinct', True)},
                'output_kind': kind, 'output': payload, 'constraints': fields.get('constraints', []),
                'priority': fields['priority'], 'min_evidence': fields['min_evidence'],
                'coverage_tag': fields['coverage_tag']})
        if not rules: raise RuleDslError('DSL has no rules')
        return CompiledRules(tuple(rules), dependencies)


def compile_rules(text, roles, dependency_versions):
    from ..syntax_rules import validate_rules
    result = Parser(text).rules()
    if any(str(dependency_versions.get(k)) != v for k, v in result.dependency_versions.items()):
        raise RuleDslError('undeclared/mismatched resource read')
    validate_rules(result.rules, roles, dependency_versions)
    return result
