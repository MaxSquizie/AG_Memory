"""TEST_ONLY Russian clock vocabulary; generic parser has no language word list."""
import re


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
