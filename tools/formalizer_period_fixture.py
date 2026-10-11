"""TEST_ONLY vocabulary for explicitly exhaustive named periods; no clock bounds."""


def rules():
    return [{'rule_id':'TEST-WHOLE-PERIOD-'+period,'kind':'NAMED_PERIOD','period_id':period,
             'pattern':pattern,'interval_semantics':'CONTINUOUS'} for period,pattern in [
        ('MORNING',r'\bвс[её]\s+утро\b'),('DAY',r'\bвесь\s+день\b'),
        ('EVENING',r'\bвесь\s+вечер\b'),('NIGHT',r'\bвсю\s+ночь\b')]]
