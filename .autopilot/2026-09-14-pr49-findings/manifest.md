# Манифест требований

Источник: `2026-09-14-brief.md` — опубликованное ревью PR #49.
Строку из этого списка может снять **только пользователь**.

| ID | Из брифа (дословно) | Статус | Основание | Где |
|----|---------------------|--------|-----------|-----|
| R01 | «an unhashable frontmatter key raises `TypeError` past every handler: traceback, no report, exit 1 instead of the documented 6» | done | таски 01 и 03, коммит 37c5295 | — |
| R02 | «only `ConvertError` is caught, so an `OSError` while reading or copying escapes: traceback, no report, exit 1, and a partially assembled tree left under `--out`» | done | таски 01 и 03, коммит 37c5295 | — |
| R03 | «it breaks the rule that every outcome still produces a report» | done | таски 01 и 03, коммит 37c5295 | — |
| R04 | «no test exercises a non-`ConvertError` exception path; the 13 `BROKEN` cases all raise inside `yaml.YAMLError` or `ConvertError`» | done | таски 01 и 03, коммит 37c5295 | — |
| R05 | «AGENTS.md §6 says repository documentation must be 100% English… This PR adds Russian prose outside it: PRD §5.1–5.3, `docs/README.md:14`, and the reworded `AGENTS.md:116-118`» | done | таск 02, коммит bf02b33 | — |
| R06 | «Two ways to close it… translate the changed prose, or record the exception in AGENTS.md §6 the way `.autopilot/` is recorded» | done | таск 02, коммит bf02b33 | — |
| R07 | «the checklist says seven postponed decisions, PRD §5 now lists six» | done | таск 02, коммит bf02b33 | — |
| R08 | «`.autopilot/dashboard.html:257` (a workstation path in the committed state — note it is already on `main`, so this PR only carries it forward). Resolve or answer them before merge» | done | таск 02, коммит bf02b33 | — |
| R09 | «a homeless *directory* earns an `advice:` line saying it stayed in the skill folder; a top-level file never does» | done | таски 01 и 03, коммит 37c5295 | — |
| R10 | «"the verdict becomes the exit code" is contradicted eleven lines down by AGENTS.md:113… One of the two lines should yield» | done | таск 02, коммит bf02b33 | — |
| R11 | «the CLI test reads both streams but never asserts an exit code» | done | таски 01 и 03, коммит 37c5295 | — |
| R12i | *(подразумевается)* правки идут в ту же ветку и тот же PR #49, а не новым PR: ревью относится к незамерженному изменению | open | — | — |
| R13i | *(подразумевается)* закрытые треды ревью получают ответ, а не молчаливую правку: две строки прямо просят «resolve or answer» | open | — | — |
| R14i | *(подразумевается)* у каждого исправленного дефекта есть тест, который краснеет без правки — иначе обе дыры вернутся | open | — | — |
