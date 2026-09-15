# 02 — Способность запретить — отдельная запись описания

**Требования:** R06, G01
**Blocked by:** —
**Зона:** `specs/`, `src/agent_skill_adapter/envspec/model.py`, `src/agent_skill_adapter/envspec/schema.py`
**Волна:** 1
**Status:** ready

## Что должно заработать

Сравнение описаний перестаёт молчать про потерянный запрет. Сейчас
`hook.event.PreToolUse` у Claude Code документирован словами «before a tool call executes;
**can block it**» — два утверждения в одной записи, из-за чего сравнение видит
«воспроизводится» и про запрет не говорит ничего.

После таска событие и способность запретить — разные записи, и пересобранный
`specs/gaps/*` показывает вторую как `unknown`.

## Из брифа, дословно

> «W1. Разделить запись в описании, а не городить особый случай в конвертере. `hook.event.PreToolUse` → две записи: событие и `hook.decision.block`. У Claude Code вторая `supported`, у Antigravity — `unknown`. Дальше правило origin отрабатывает само.»

## Разделы спецификации

История 5, Решения §«Hooks — правится описание, а не конвертер».

## Критерии приёмки

- [ ] `Capability.kind` принимает новое значение `hook-decision`; остальные четыре не тронуты
- [ ] `specs/anthropic/claude-code-2.1.yaml`: запись `hook.decision.block`, `support: supported`,
      `source_id` указывает на тот раздел документации, который про запрет и говорит
- [ ] `specs/google/antigravity-2.0.yaml`: запись `hook.decision.block`, `support: unknown`,
      в `note` сказано, что страница про поведение при ненулевом коде возврата молчит —
      и это молчание, а не отказ
- [ ] `specs/schema/envspec.schema.json` пересобран (`make schema`)
- [ ] `specs/gaps/*` пересобраны командой `gaps`; в отчёте появилась строка `hook.decision.block`
      с исходом `unknown`
- [ ] Тест: описание с записью вида `hook-decision` грузится и попадает в сравнение
- [ ] `make check` зелёный, включая `test_committed_schema_matches_the_model`
      и `test_committed_report_matches_the_descriptions_it_was_built_from`
