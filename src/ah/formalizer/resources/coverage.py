"""Coverage artifact validation; lexical availability never implies G5 PASS."""
from __future__ import annotations
import re

CATEGORIES={'COVERED','NOT_COVERED','KNOWLEDGE_ABSENT','OOV_KEEP_AS_IS'}


def validate_coverage(report,content_sha256,resources):
    required={'corpus_id','corpus_sha256','units_by_kind','categories','resource_content_sha256','measurement_kind'}
    if (not isinstance(report,dict) or not required<=set(report)
            or not isinstance(report['corpus_id'],str) or not report['corpus_id']
            or not isinstance(report['corpus_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',report['corpus_sha256'])
            or report['resource_content_sha256']!=content_sha256
            or report['measurement_kind'] not in {'RESOURCE_LEXICAL_AVAILABILITY','REVIEWED_EXECUTION_COVERAGE'}):
        raise ValueError('invalid/unbound coverage report')
    for key in ('units_by_kind','categories'):
        if not isinstance(report[key],dict) or any(type(n) is not int or n<0 for n in report[key].values()):
            raise ValueError('invalid coverage counts')
    if set(report['categories'])!=CATEGORIES or set(report['units_by_kind'])!=set(resources):
        raise ValueError('coverage must name all categories and resource kinds')
    if report['measurement_kind']=='RESOURCE_LEXICAL_AVAILABILITY':
        if report.get('execution_coverage') is not None: raise ValueError('lexical report cannot assert execution coverage')
        rows=report.get('measured_units')
        if not isinstance(rows,list) or sum(report['categories'].values())!=len(rows):
            raise ValueError('lexical observations/counts disagree')
        from collections import Counter
        seen=set(); counts=Counter()
        for row in rows:
            if (not isinstance(row,dict) or set(row)!={'unit_id','range','surface','category'}
                    or row['category'] not in CATEGORIES or not isinstance(row['unit_id'],str) or not row['unit_id']
                    or not isinstance(row['surface'],str) or not row['surface']
                    or not isinstance(row['range'],list) or len(row['range'])!=2
                    or any(type(n) is not int or n<0 for n in row['range']) or row['range'][0]>=row['range'][1]):
                raise ValueError('invalid measured lexical unit')
            key=(row['unit_id'],*row['range'])
            if key in seen: raise ValueError('duplicate measured lexical unit')
            seen.add(key); counts[row['category']]+=1
        if any(counts[k]!=report['categories'][k] for k in CATEGORIES): raise ValueError('category counts disagree')
    else:
        if not isinstance(report.get('execution_coverage'),dict) or not report.get('evidence_artifacts'):
            raise ValueError('execution coverage requires measured artifact refs')
