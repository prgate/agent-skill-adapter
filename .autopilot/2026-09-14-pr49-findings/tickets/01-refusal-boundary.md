# 01 — Граница отказа: отчёт при любом исходе

**Требования:** R01, R02, R02.1, R03, R04, R09, R11, R14i
**Blocked by:** —
**Зона:** `src/agent_skill_adapter/convert.py`, `tests/unit/test_convert.py`
**Волна:** 1
**Status:** ready

## Что должно заработать

Ни один вход не заставляет команду напечатать трассировку и выйти кодом 1. Код 1 означает
«перенёс, потери известны» — это разрешающий итог, и автоматика, читающая код возврата,
на сломанном входе сейчас получает «всё в порядке».

## Из брифа, дословно

> «an unhashable frontmatter key raises `TypeError` past every handler: traceback, no report, exit 1 instead of the documented 6»

> «only `ConvertError` is caught, so an `OSError` while reading or copying escapes: traceback, no report, exit 1, and a partially assembled tree left under `--out`»

> «it breaks the rule that every outcome still produces a report»

> «no test exercises a non-`ConvertError` exception path; the 13 `BROKEN` cases all raise inside `yaml.YAMLError` or `ConvertError`»

> «a homeless *directory* earns an `advice:` line saying it stayed in the skill folder; a top-level file never does»

> «the CLI test reads both streams but never asserts an exit code»

## Разделы спецификации

Истории 1–7; Решения §«Отказ ловится по границе», §«Нехешируемый ключ», §«Под `--out`
не остаётся половины», §«Файл верхнего уровня»; Границы и швы.

## Критерии приёмки

- [ ] Заголовок с нехешируемым ключом (`? [a, b]` / `: v`) даёт код 6 и отчёт в stdout.
      Проверка `key in seen` больше не перехватывает то, что конструктор PyYAML отвергнет сам
- [ ] Ошибка файловой системы приходит в тот же путь отказа, что коды 6, 7 и 8: отчёт есть,
      сводка есть, код процесса равен `exit_code` в отчёте. Сторона решает код: чтение папки
      скилла — 6 («исходные настройки не прочитаны»), сборка под `--out` — 7 («записать
      не смогли», тот же, что у выхода за корень). Третьего кода не заводить
- [ ] Висячая ссылка внутри папки бандла (`scripts/dangling -> /nonexistent`) не даёт
      ни трассировки, ни кода 1
- [ ] После сорвавшейся сборки под `--out` не остаётся половины результата, и `written` пуст
- [ ] Нечитаемый `SKILL.md` (права, ошибка `stat`) идёт тем же путём
- [ ] Файл верхнего уровня, которому не нашлось места, получает строку `advice` — как её
      получает бездомная папка
- [ ] Тест CLI утверждает код возврата 0 на обоих вызовах, а не только содержимое потоков
- [ ] На каждый из двух дефектов есть случай, **красный без правки** — покажи это в отчёте
- [ ] `make check` и `make pre-commit-run` зелёные
