"""TEST_ONLY Russian clock vocabulary; generic parser has no language word list."""
import re


def bound_rules():
    # Forms are resource data. Runtime stores the captured phrase unchanged;
    # these entries deliberately contain no numeric interpretation or hours.
    forms = ['одного','двух','трех','трёх','четырех','четырёх','пяти','шести',
             'семи','восьми','девяти','десяти','одиннадцати','двенадцати']
    atoms = '(?:[0-9]{1,2}|'+'|'.join(map(re.escape, forms))+')'
    anchor = atoms+r'\s+(?:часа|часов)\b'
    return [{'rule_id':'TEST-SYMBOLIC-BOUND-'+op, 'kind':'TEMPORAL_BOUND', 'operator':op,
             'pattern':r'\b'+word+r'\s+(?P<anchor>'+anchor+')'}
            for word,op in [('до','BEFORE'),('после','AFTER')]]


def clock_rule():
    atoms = ['ноль','один','два','три','четыре','пять','шесть','семь','восемь','девять',
             'десять','одиннадцать','двенадцать','тринадцать','четырнадцать',
             'пятнадцать','шестнадцать','семнадцать','восемнадцать','девятнадцать']
    values = {word:n for n, word in enumerate(atoms)}
    values.update({'одна':1,'одно':1,'одну':1,'две':2,
                   'двадцать':20,'тридцать':30,'сорок':40,'пятьдесят':50,
                   'шестьдесят':60,'семьдесят':70,'восемьдесят':80,'девяносто':90})
    atom = '(?:[0-9]{1,2}|'+'|'.join(re.escape(w) for w in sorted(values, key=lambda w:(-len(w),w)))+')'
    number = atom+'(?:\\s+'+atom+'){0,2}'
    pattern = r'\bв\s+(?P<hour>'+number+r')\s+(?:часа|часов|час)\b(?:\s+(?P<minute>'+number+r')\s+(?:минуты|минуту|минута|минут)\b)?'
    return {'rule_id':'TEST-WORD-CLOCK-1','kind':'WORD_CLOCK', 'pattern':pattern,
            'number_values':values, 'clock_cycle':12}


def range_rule():
    clock = clock_rule()
    # Explicit test lexicon: boundary forms and fixed civil anchors are data.
    end = dict(clock, pattern=clock['pattern'].replace(r'\bв\s+', r'\bдо\s+'))
    return {'rule_id':'TEST-CLOCK-RANGE-1','kind':'CLOCK_RANGE',
        'pattern':r'(?P<start>\bс\s+полудня\b)[^.!?;]*?(?P<end>'+end['pattern']+')',
        'start_clock':{'kind':'FIXED','hour':12,'minute':0}, 'end_clock':end,
        'end_day_offsets':[0,1], 'interval_semantics':'EXISTENTIAL'}
