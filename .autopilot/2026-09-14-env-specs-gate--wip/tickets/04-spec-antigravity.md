# 04 — Описание среды Google Antigravity

**Требования:** R03, R05, R21, R26, R27, R33i
**Blocked by:** 01
**Зона:** `specs/google/`
**Волна:** 2
**Status:** ready

## Что должно заработать

Файл `specs/google/antigravity-2.0.yaml` — описание целевой среды по официальной документации.

Источник — `https://antigravity.google/docs/*`. Markdown-версия страницы — тот же адрес с `.md`
(`https://antigravity.google/docs/skills.md`), полный список страниц — `https://antigravity.google/llms.txt`.
Загружать: `curl -sS --compressed -A "Mozilla/5.0" -L`. Хеш — по правилу `normalization: v1`
(модуль `envspec.normalize` из таска 01).

Страницы, с которых надо начать (проверено, они существуют):
`docs/skills`, `docs/hooks`, `docs/subagents`, `docs/permissions`, `docs/agent-settings`,
`docs/settings`, `docs/rules-workflows`, `docs/plugins`, `docs/mcp`;
CLI-часть: `docs/cli/subagents`, `docs/cli/permissions`, `docs/cli/settings`, `docs/cli/plugins`;
IDE-часть: `docs/ide/skills`, `docs/ide/hooks`, `docs/ide/rules`, `docs/ide/settings`.

Заполняются: `capabilities` (по тем же четырём видам, что и у Claude Code — так их потом
сравнивать), `limits` (пределы размера файла скилла и набора, с явной единицей),
`tool_names` (таблица соответствия имён инструментов агента: `from` — имя в Claude Code,
`to` — имя в Antigravity, с `source_id`).

**Ключевое правило этого таска:** запись `support: unsupported` ставится только тогда, когда
документация **прямо говорит**, что этого нет. Документация молчит — `unknown`.
Разница между «сказано нет» и «не сказано ничего» — то, ради чего собираются эти описания.
Соответствия имени инструмента нет — записи в `tool_names` просто нет; похожее по смыслу
не подставлять.

**Версия среды:** Antigravity 2.0, `version_range` — `">=2.0.0,<3.0.0"`, пока документация
не даст более точной привязки.

## Из брифа, дословно

> «В первую версию входят два описания: Claude Code как источник и Google Antigravity как цель» (FR-11)
> «Названия инструментов агента внутри инструкций переписываются под целевую среду по таблице
> соответствий из её описания» (FR-30)
> «Свойство, которого нет в описании, считается неизвестным, а не поддерживаемым» (FR-12)

## Разделы спецификации

Истории 1–2, 17–18. Решения §«Оценка поддержки», §«Свойство, которого нет в описании».

## Критерии приёмки

- [ ] `envspec.loader.load()` читает файл без ошибок схемы
- [ ] У каждого источника заполнены `url`, `markdown_url`, `anchor`, `sha256`, `checked_at`,
      `environment_version`; `sha256` совпадает с пересчётом от живой страницы
- [ ] Покрыты четыре вида записей — те же, что в описании Claude Code
- [ ] `tool_names` заполнена по документации; пары, которой в документации нет, в таблице нет
- [ ] `limits` с явной единицей измерения
- [ ] Ни одного `unsupported` без цитаты документации в `note`
- [ ] Заполнен `layout:` — где Antigravity держит скиллы, субагентов, настройки и hooks
- [ ] Перечень тем совпадает с описанием Claude Code: по каждому полю/событию из таска 03
      в описании Antigravity есть запись — `supported`, `unsupported` или `unknown`
