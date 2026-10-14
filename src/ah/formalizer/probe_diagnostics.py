"""Inspect the actual probe wiring; never enable calls or alter a release."""


def describe(adapter, config=None):
    release=getattr(adapter,'_release',None)
    entries=release.entries('ProposalPolicy') if release is not None else ()
    composition=entries[0].get('composition') if entries else None
    return {'adapter_available':adapter is not None,
            'selector':type(adapter._selector).__name__ if getattr(adapter,'_selector',None) is not None else None,
            'structure_mode':getattr(adapter,'_structure_mode',None),
            'composition_enabled':bool(composition),
            'release_sha256':getattr(release,'sha256',None),
            'config_path':str(config.source_path) if getattr(config,'source_path',None) else None,
            'data_dir':str(config.paths.data_dir) if getattr(config,'paths',None) else None}


def configuration_text(info):
    if not info:return 'Сведения о подключении проб не сохранены.'
    if not info.get('adapter_available'):return 'Формализатор не подключён. Пробы недоступны.'
    if not info.get('selector'):return 'Поставщик ответов для проб не подключён.'
    if info.get('structure_mode')!='region_probes':return 'Активен другой режим разбора; требуется region_probes.'
    if not info.get('composition_enabled'):
        return ('В активных ресурсах НЕТ компонентов композиции. Пробы границ, ролей и областей действия недоступны. '
                'Для текущего стенда запустите run_formalizer_lab.bat; старую память и релиз не заменяйте.')
    return 'Композиционные пробы включены. Вопросы передаются подключённому backend модели при необходимости.'


def activity(events):
    return {'started':events.get('probe_started',0),'finished':events.get('probe_finished',0),
            'failed':events.get('probe_failed',0),'replayed':events.get('probe_replayed',0),
            'input_reused':events.get('document_input_reused',0)>0}


def activity_text(info):
    if info is None:return 'Число вызовов модели в этом запуске не сохранено.'
    text=(f"Вызовы модели: {info['started']}; ответов: {info['finished']}; ошибок: {info['failed']}. "
          f"Ответов из журнала без вызова модели: {info['replayed']}.")
    if info.get('input_reused'):text+=' Использован ранее зарегистрированный вход.'
    if not info['started']:
        text+=' В этом запуске модель для проб не вызывалась.'
        if not info['replayed'] and not info.get('input_reused'):
            text+=' Проверьте профиль и решения: разбор мог завершиться алгоритмически или остановиться до вопроса.'
    return text
