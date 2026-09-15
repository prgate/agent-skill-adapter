# 01 — Побеждает последний: два места, где значение исчезает молча

**Требования:** R01, R02, R03, R04, R05, R07i, R09i
**Blocked by:** —
**Зона:** `src/agent_skill_adapter/convert.py`, `tests/unit/test_convert.py`
**Волна:** 1
**Status:** ready

## Что должно заработать

Ни одно значение не пропадает из-за того, что два имени стали одним.

Воспроизведено до начала работ: скилл с

```yaml
hooks:
  PreToolUse:
    2026-09-14: from-date-key
    "2026-09-14": from-string-key
```

даёт код 1 и `hooks.json`, где остался только `from-string-key`. `from-date-key` не
упомянут нигде — ни в отчёте, ни в `advice`.

## Из ревью, дословно

> «A YAML date key and an equivalent quoted string key are distinct before this conversion but both become the same string key here… cause one value to overwrite the other before `hooks.json` is written. Normalize mapping keys into a temporary mapping and refuse duplicate normalized keys.»

> «It does not detect two planned parts that expand to the same staged path… The later `copy2` overwrites the earlier file, while `written` reports both as successful. Validate that planned staged paths are unique and do not overlap before the write loop. Return `COLLISION` when they do.»

> «A concurrent writer can replace a checked path component with a symlink, causing `mkdir()` or subsequent writes to escape `out`… Reject symlinks during every destination-path operation.»

## Разделы спецификации

Истории 1–4; Решения §«Ключи схлопываются», §«План проверяется на пересечение», §«Гонка сужается».

## Критерии приёмки

- [ ] Два разных ключа YAML, давших один нормализованный, — отказ кодом 6 тем же путём,
      что дублирующийся ключ. Не заводи для него второй вид отказа: это и есть дубликат,
      просто возникший после нашей нормализации
- [ ] Сообщение называет путь внутри заголовка и оба исходных написания
- [ ] Случай в таблице `BROKEN` рядом с `duplicate-key`
- [ ] Два куска плана, метящие в один путь назначения, дают код 8 **до первой записи**,
      и `written` пуст. Проверка плана на самопересечение — отдельно от проверки
      на существующее
- [ ] Символическая ссылка отвергается на **каждом** уровне пути назначения, а не только
      на конечном, и проверка стоит непосредственно перед операцией
- [ ] Остаток гонки помечен `# ponytail:` с указанием на FR-14 и словами, что окно сужено,
      а не закрыто
- [ ] На дефект с ключами и на пересечение плана есть тесты, **красные без правки** —
      покажи в отчёте, чем именно краснели
- [ ] `make check` и `make pre-commit-run` зелёные
