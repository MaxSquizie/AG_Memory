"""Released scalar notation on a typed value argument; no numeric name guessing."""
import re
from decimal import Decimal, InvalidOperation


def scalar_property(raw,schema):
    syntax=schema.get('literal_syntax')
    if syntax is None: return None
    if not isinstance(raw,str) or len(raw)>80: raise ValueError('SCALAR_VALUE_INVALID')
    patterns={'INTEGER':r'[+-]?[0-9]+','DECIMAL_DOT':r'[+-]?[0-9]+(?:\.[0-9]+)?',
              'DECIMAL_COMMA':r'[+-]?[0-9]+(?:,[0-9]+)?'}
    value=raw.strip()
    if not re.fullmatch(patterns[syntax],value): return None
    try: number=Decimal(value.replace(',','.'))
    except InvalidOperation as exc: raise ValueError('SCALAR_VALUE_INVALID') from exc
    if not number.is_finite(): raise ValueError('SCALAR_VALUE_INVALID')
    return {'name':schema['numeric_property'],'value':str(number),'type_name':'decimal','unit':schema['unit']}
