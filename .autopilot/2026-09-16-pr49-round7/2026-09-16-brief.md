# Бриф: закрыть находки ревью PR #49, раунд 7

Ревью: https://github.com/prgate/agent-skill-adapter/pull/49#pullrequestreview-5215040857
Ветка `feature/skill-convert-slice`, worktree `.worktrees/convert`, HEAD `9969fd2`.
Все находки воспроизведены локально запуском на этом HEAD (2026-09-15).

## Root cause по находкам

| # | Находка | Root cause |
|---|---|---|
| A 🔴 | CRLF `SKILL.md` → exit 6 | `FRONTMATTER_CLOSE = r"\n---[ \t]*(?:\n|\Z)"` требует голый `\n` с обеих сторон; `\r` не входит ни в `[ \t]`, ни в `\n`. Старый скан `\n---` ловил CRLF случайно. CRLF-тестов нет. |
| B 🟡 | symlink-`SKILL.md` не раскрыт | `9969fd2` одним предикатом `label != SKILL_MD` решил два вопроса: *как копировать* (через линк — верно) и *раскрывать ли* (выкинул — неверно). Тест `test_a_skill_file_that_is_a_symbolic_link_is_read_and_assembled_whole` (~918) прибивает **отсутствие** раскрытия. |
| C 🟡 | `..` в `--out` режет проверку уровней | `out` в двух написаниях: `_under()` нормализует `out / staged`, `_links_on_the_way()` сравнивает `staged.parents` с сырым `out`. Лексический `is_relative_to` → `False` → `below == []`. Сырой `a/../b` → 0 уровней, нормализованный → 3. |
| D 🟡 | stderr forging | `_summary()` — единственный sink текста для человека, интерполирует ключи frontmatter, имена файлов, текст YAML-ошибок без экранирования. JSON безопасен (`json.dumps`). Ключ `"x\n  clean ..."` даёт поддельную строку, `[2J` — сырой ESC. |
| E 🟡 | `chmod(0o000)` без `skipif` | Тест на ~1005 скопирован без декоратора, который есть у соседей (308, 329). |
| F 🟡 | 102 / 115 / 160 | Число тестов захардкожено в прозе, дрейфует каждым коммитом, флагуется второй раунд. |
| G 🟡 | hook-строка с сырым шаблоном | Два пути строят `destination`: части скилла через `_destination()`, hook-часть получает сырую строку `_layout()` из `_hook_place`. Shipped spec спеллит `hooks.project` без префикса и маскирует баг; `hooks.user` (`~/...`) и любой `<workspace-root>/`-путь показывают сырьё. |

Optional: `_assembled_name` exit 6 vs 3 — реально (`environment: str = Field(min_length=1)`).
CWE-367 — оставить, deferral задокументирован в `# ponytail:` → FR-14.

## Инструкции

Порядок строго: RED-тест → фикс → `make check` → отдельный коммит (Conventional Commits,
английский). Не трогать `specs/google/*.yaml`, `specs/gaps/*`, `specs/schema/*`,
`docs/converting-a-real-skill.md` — ни одно изменение ниже не меняет записанный там вывод.
`AGENTS.md` ≤ 120 строк (сейчас 119).

### 1. [CRITICAL] CRLF frontmatter — `src/agent_skill_adapter/convert.py:226`

RED: тест рядом с `test_a_line_only_starting_with_three_dashes_does_not_close_the_frontmatter`
(~812): `SKILL.md` записан как bytes
`b"---\r\ndescription: what it does\r\nname: example\r\n---\r\n\r\nBody.\r\n"`;
assert `exit_code != 6` и `report["skill"]["name"] == "example"`.

FIX: `FRONTMATTER_CLOSE = re.compile(r"\r?\n---[ \t]*(?:\r?\n|\Z)")`.
В docstring одна фраза: CRLF-концы строк закрывают заголовок так же, как LF.

НЕ делать `text.replace("\r\n", "\n")` и не нормализовать байты при копировании: файл
копируется как есть, меняется только распознавание закрывающей строки. Проверить, что
существующие кейсы (`----`, отступ перед `---`, `---note:`, EOF без `\n`, незакрытый
заголовок) остались в прежнем статусе.

### 2. [REQUIRED, тривиальные — один коммит]

a) `tests/unit/test_convert.py:1005` `test_a_copy_that_fails_part_way_leaves_no_half_assembled_skill`:
   добавить декоратор со строк 308/329:
   `@pytest.mark.skipif(os.geteuid() == 0, reason="a mode of 000 does not stop root from reading")`.

b) `INVALID_NAMES` (~638): добавить `"widget\n"` и `"../evil"`. `json.dumps` в тесте уже
   кодирует их как YAML double-quoted строки; код не менять, тест пройдёт сразу — это
   пиннинг `fullmatch` против `match`.

c) `AGENTS.md:103`: убрать число из строки про `make check` — оставить
   «ruff + mypy strict + pytest». Число тестов остаётся только в теле PR и ставится
   ПОСЛЕДНИМ шагом (п. 8) из реального вывода `make check`.

### 3. [REQUIRED] Hook-часть мимо `_destination` — `convert.py:_plan` (~871)

RED: в `hooks_tree` (~397) путь `hooks.project` заменить на
`"<workspace-root>/.agents/hooks.json"` (в стиле `skills.project` там же). Существующий
`test_only_a_hook_the_target_fires_is_staged_and_the_report_says_where_it_belongs` ожидает
`"to": ".agents/hooks.json"` и упадёт — это RED. Нового теста не писать.

FIX: в `_plan` после `_hook_place`:
```python
where, _ = _destination(hooks_file, assembled_name)
hook_part = _hook_part(out, where, carried)
```
`Path(where).name` по-прежнему `hooks.json`, staged-путь не меняется. Реальный spec не
править: `_destination` обрабатывает оба написания.

### 4. [REQUIRED] `..` в `--out` — `convert.py:_links_on_the_way` (~1041)

RED: параметризовать `test_a_link_partway_down_the_destination_is_not_written_through`
(~1397) по написанию out: `tmp_path/"out"` и `tmp_path/"a"/".."/"out"` (каталог `a`
создать). Со вторым написанием линк `.agents` сейчас не ловится (upfront-проверка в
`_assemble` резолвит через линк и видит путь под out), файл пишется через линк — тест ждёт
exit 7 и падает.

FIX: одна нормализация в одном месте — в `convert()`:
```python
out_dir = Path(os.path.normpath(out)) if out is not None else None
```
передавать `out_dir` в `_plan` и `_assemble` вместо `Path(out)`. Тогда `_under`,
`_links_on_the_way` и тексты ошибок видят одно написание.

НЕ добавлять второй `normpath` внутрь `_links_on_the_way` — снова два написания.

### 5. [REQUIRED] Раскрытие symlink-`SKILL.md` — `_links_within` (~1076) и ~1259

RED: в `test_a_skill_file_that_is_a_symbolic_link_is_read_and_assembled_whole` (~893)
ПЕРЕВЕРНУТЬ последний assert: advice ДОЛЖЕН содержать строку, где есть `"SKILL.md"`,
`"symbolic link"` и `str(real / "SKILL.md")`. Verdict CLEAN / exit 0 оставить: это
раскрытие, не потеря. Второй тест на то же не писать.

FIX (ровно два места):
- в `_links_within` ветка `is_symlink()`: если `label == SKILL_MD`, вернуть
  ``[f"`{SKILL_MD}` is a symbolic link to {os.readlink(copied_from)}; its content was read and copied, not the link"]``.
  Формулировка обязана говорить «прочитан и скопирован», а не «not read» — `_frontmatter`
  его прочитал. Иначе — старое сообщение. `os.readlink`, а не `resolve()`: показывает то,
  что написано в линке, и не бросает на петле (петля на `SKILL.md` уже отсекается в
  `_frontmatter` как exit 6).
- в comprehension `links = [...]` (~1259) убрать `and part.label != SKILL_MD`.

НЕ трогать `and part.label != SKILL_MD` в ветке копирования (~1219): там исключение
правильное.

### 6. [REQUIRED] Управляющие символы в stderr — `_summary` (~1370)

RED: `SKILL.md` с ключами
```yaml
"x\n  clean        forged.row -- injected (reproduced, specification)": 1
"[2Jwiped": 2
```
```python
assert "\x1b" not in result.summary
assert not any(line.startswith("  clean        forged.row") for line in result.summary.splitlines())
```

FIX: экранировать на sink, построчно:
```python
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

def _plain(line: str) -> str:
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}", line)
...
return "\n".join(_plain(line) for line in lines) + "\n"
```
Именно построчно, до join: разделители самого summary не трогать. Не экранировать в
`_findings`/`_as_spelled` — точек входа много, sink один. JSON-отчёт не менять. Известный
побочный эффект: многострочная ошибка PyYAML станет одной строкой с литеральным `\x0a` —
приемлемо, ни один тест не проверяет текст summary. U+2028/U+2029 и bidi-override
сознательно не покрываем.

### 7. [OPTIONAL, отдельными коммитами]

a) Nested-link label: `scripts/inner/link -> куда угодно`; assert строка advice содержит
   `` `scripts/inner/link` ``. Кода не менять — пиннинг формата.
b) `_assembled_name` (~783): перед склейкой
   `if not _valid_name(environment): raise ConvertError(..., EXIT_CODE[Verdict.UNDECIDABLE])`
   — вина описания, код 3. Переполнение длины оставить на 6. Тест со своим
   target-описанием `environment="Anti_Gravity"` и своей ссылкой `vendor/env@version`.
c) CWE-367 в `_assemble` — НЕ трогать.

### 8. Финал

`make check` и `make pre-commit-run` зелёные; число passed из ЭТОГО прогона записать в
тело PR (`gh pr edit 49 --body-file`), больше нигде. Затем перезапустить ревью чекбоксом
«Trigger PRgate review».
