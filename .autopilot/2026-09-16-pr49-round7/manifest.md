# Манифест требований

Источник: `2026-09-16-brief.md`. Строку из этого списка может снять **только пользователь**.

Особенность прогона: пункты 1–7 брифа были выполнены предыдущей сессией (коммиты
`1f46ea6..f877d60`) до очистки контекста. Этот прогон сверяет каждое требование с
коммитами, закрывает пункт 8 и оставляет запись.

| ID | Из брифа (дословно) | Статус | Основание | Где |
|----|---------------------|--------|-----------|-----|
| R01 | «`FRONTMATTER_CLOSE = re.compile(r"\r?\n---[ \t]*(?:\r?\n|\Z)")`» + RED-тест на CRLF | in-ticket | — | T01 |
| R02 | «В docstring одна фраза: CRLF-концы строк закрывают заголовок так же, как LF» | in-ticket | — | T01 |
| R03 | «НЕ делать `text.replace("\r\n", "\n")` и не нормализовать байты при копировании» | in-ticket | — | T01 |
| R04 | «добавить декоратор со строк 308/329: `@pytest.mark.skipif(os.geteuid() == 0, ...)`» | in-ticket | — | T02 |
| R05 | «`INVALID_NAMES` (~638): добавить `"widget\n"` и `"../evil"`... код не менять» | in-ticket | — | T02 |
| R06 | «`AGENTS.md:103`: убрать число из строки про `make check`» | in-ticket | — | T02 |
| R07 | «в `_plan` после `_hook_place`: `where, _ = _destination(hooks_file, assembled_name)`» | in-ticket | — | T03 |
| R08 | «в `hooks_tree` (~397) путь `hooks.project` заменить на `"<workspace-root>/.agents/hooks.json"`» | in-ticket | — | T03 |
| R09 | «одна нормализация в одном месте — в `convert()`: `out_dir = Path(os.path.normpath(out))`» | in-ticket | — | T04 |
| R10 | «параметризовать `test_a_link_partway_down_the_destination_is_not_written_through` по написанию out» | in-ticket | — | T04 |
| R11 | «в `_links_within` ветка `is_symlink()`: если `label == SKILL_MD`, вернуть ... `os.readlink`» | in-ticket | — | T05 |
| R12 | «в comprehension `links = [...]` (~1259) убрать `and part.label != SKILL_MD`» | in-ticket | — | T05 |
| R13 | «НЕ трогать `and part.label != SKILL_MD` в ветке копирования (~1219)» | in-ticket | — | T05 |
| R14 | «ПЕРЕВЕРНУТЬ последний assert... Verdict CLEAN / exit 0 оставить» | in-ticket | — | T05 |
| R15 | «экранировать на sink, построчно: `_CONTROL`, `_plain`, `"\n".join(_plain(line) ...)`» | in-ticket | — | T06 |
| R16 | «Не экранировать в `_findings`/`_as_spelled`... JSON-отчёт не менять» | in-ticket | — | T06 |
| R17 | «Nested-link label... assert строка advice содержит `` `scripts/inner/link` ``. Кода не менять» | in-ticket | — | T07 |
| R18 | «`_assembled_name` (~783): перед склейкой `if not _valid_name(environment): raise ConvertError(..., EXIT_CODE[Verdict.UNDECIDABLE])`» | in-ticket | — | T07 |
| R19 | «CWE-367 в `_assemble` — НЕ трогать» | in-ticket | — | T07 |
| R20 | «Порядок строго: RED-тест → фикс → `make check` → отдельный коммит (Conventional Commits, английский)» | in-ticket | — | T01–T07 |
| R21 | «Не трогать `specs/google/*.yaml`, `specs/gaps/*`, `specs/schema/*`, `docs/converting-a-real-skill.md`» | in-ticket | — | T01–T07 |
| R22 | «`AGENTS.md` ≤ 120 строк» | in-ticket | — | T02 |
| R23 | «`make check` и `make pre-commit-run` зелёные» | in-ticket | — | T08 |
| R24 | «число passed из ЭТОГО прогона записать в тело PR (`gh pr edit 49 --body-file`), больше нигде» | in-ticket | — | T08 |
| R25 | «Затем перезапустить ревью чекбоксом «Trigger PRgate review»» | in-ticket | — | T08 |
