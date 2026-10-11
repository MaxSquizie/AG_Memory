"""Explicit TEST_ONLY calendar vocabulary; runtime has no Russian date constants."""
import re


def policy():
    ordinals=['первого','второго','третьего','четвертого','пятого','шестого','седьмого',
              'восьмого','девятого','десятого','одиннадцатого','двенадцатого','тринадцатого',
              'четырнадцатого','пятнадцатого','шестнадцатого','семнадцатого','восемнадцатого','девятнадцатого','двадцатого']
    days={w:i+1 for i,w in enumerate(ordinals)}
    days.update({'двадцать '+w:21+i for i,w in enumerate(ordinals[:9])})
    days.update({'тридцатого':30,'тридцать первого':31})
    days.update({str(i):i for i in range(1,32)})
    months={w:i+1 for i,w in enumerate(['января','февраля','марта','апреля','мая','июня',
                                     'июля','августа','сентября','октября','ноября','декабря'])}
    weekdays=['понедельник','вторник','среда','четверг','пятница','суббота','воскресенье']
    alternatives=lambda values:'|'.join(re.escape(w) for w in sorted(values,key=lambda x:(-len(x),x)))
    pattern=r'(?P<day>'+alternatives(days)+r')\s+(?P<month>'+alternatives(months)+r')(?:\s+(?P<year>\d{4})(?:\s+года)?)?\.?\s*(?P<weekday>'+alternatives(weekdays)+r')?\.?'
    return {'version':'CALENDAR_AREAS_V1','context_chars':512,'rules':[
        {'rule_id':'TEST-CALENDAR-HEADER','pattern':pattern,'days':days,'months':months}]}


def periods():
    return [{'rule_id':'TEST-PERIOD-'+period,'kind':'NAMED_PERIOD','period_id':period,
             'pattern':pattern,'interval_semantics':'EXISTENTIAL'} for period,pattern in [
        ('MORNING',r'\bутром\b'),('DAY',r'\bдн[её]м\b'),
        ('EVENING',r'\bвечером\b'),('NIGHT',r'\bночью\b')]]
