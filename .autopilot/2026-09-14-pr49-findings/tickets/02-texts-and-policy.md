# 02 — Тексты и политика языка

**Требования:** R05, R06, R07, R08, R10
**Blocked by:** —
**Зона:** `AGENTS.md`, `.autopilot/` (кроме папки текущего прогона)
**Волна:** 1
**Status:** ready

## Что должно заработать

Четыре текста перестают спорить с репозиторием и друг с другом.

## Из брифа, дословно

> «AGENTS.md §6 says repository documentation must be 100% English… This PR adds Russian prose outside it»

> «record the exception in AGENTS.md §6 the way `.autopilot/` is recorded — the Russian PRD and the `README.md` / `README.en.md` pair already show the intent, they are just not written into the policy»

> «the checklist says seven postponed decisions, PRD §5 now lists six»

> «`.autopilot/dashboard.html:257` (a workstation path in the committed state)»

> «"the verdict becomes the exit code" is contradicted eleven lines down by AGENTS.md:113»

## Решение пользователя, снимающее выбор

> «Записать исключение в политику. AGENTS.md §6 перечисляет исключения явно: `.autopilot/`
> уже там, добавляются PRD и русские README.» PRD **остаётся русским целиком** — переводить
> его не надо ни целиком, ни по разделам.

## Критерии приёмки

- [ ] Раздел «How Autopilot works here» в `AGENTS.md` переведён на английский: он внутри
      маркеров, но не подпадает ни под одно исключение — это не `.autopilot/`, не PRD
      и не README. Файл, объявляющий политику, не должен нарушать её собственным текстом
- [ ] `AGENTS.md` §6 называет исключения явно: `.autopilot/`, `docs/prd/`, русскоязычные
      README (`README.md` в корне — при английском `README.en.md` рядом — и `docs/README.md`).
      Формулировка описывает то, что в репозитории уже есть, а не вводит новое правило.
      §6 лежит **вне** маркеров `autopilot:start`/`end` — это конституция репозитория,
      правь её бережно и минимально
- [ ] Строка `AGENTS.md:64` («the verdict becomes the exit code») перестаёт спорить со строкой
      про коды одиннадцатью строками ниже: вердикт даёт 0/1/3, отказы — свои коды
- [ ] `.autopilot/2026-09-14-skill-convert-slice/tickets/01-decisions.md`: «семь» → «шесть».
      Сверь по `docs/prd/PRD-001-agent-skill-adapter.md` §5, сколько строк там осталось,
      и напиши настоящее число, а не подставленное из ревью
- [ ] `skillDir` записан через `~`, без имени пользователя, в `state.js` **закрытых** прогонов:
      `.autopilot/2026-09-14-env-specs-gate/state.js` и
      `.autopilot/2026-09-14-skill-convert-slice/state.js`.
      `dashboard.html` руками не правь — его снимок перезаписывает `sync.py`, это моя часть
- [ ] Папку `.autopilot/2026-09-14-pr49-findings--wip/` не трогай — это текущий прогон,
      его ведёт оркестратор
- [ ] `make check` и `make pre-commit-run` зелёные (за длиной `AGENTS.md` следит тест:
      не больше 120 строк)
