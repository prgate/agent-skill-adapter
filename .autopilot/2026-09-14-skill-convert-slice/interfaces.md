# Границы и контракты прогона

Читается каждым субагентом перед первой строкой кода. Границы решены в спецификации —
здесь они скопированы, а не придуманы заново.

## Правила проекта, которые нельзя вывести из кода

- Python 3.10, uv-окружение `.venv`. Зависимости: pydantic, pyyaml, typer, rich.
  **Новая зависимость — CFP Level 3: не ставить, вернуться с `BLOCKED`.**
- Гейт: `make check` — ruff, `ruff format --check`, mypy strict по `src tests`, pytest.
  Таск не сдан, пока `make check` не зелёный.
- ruff: `line-length = 100`, target py310, правила `E W F I B UP`. mypy strict.
- Английский везде, кроме `.autopilot/` (русский, запись прогона).
- Осознанное упрощение помечается комментарием `# ponytail:` с потолком и путём наверх.
- Правка `model.py` оставляет позади `specs/schema/envspec.schema.json` — чинится `make schema`.
- Правка описания среды оставляет позади `specs/gaps/*` — чинится
  `uv run python -m agent_skill_adapter.envspec.gaps`.
- `urllib`/`http`/`socket`/`requests`/`httpx` вне `freshness.py` роняют
  `test_only_the_freshness_module_may_reach_the_network`.
- Работа ведётся в worktree `.worktrees/<slug>`, ветка `<type>/<kebab-case>`,
  коммиты Conventional Commits.

## Границы, решённые в спецификации

| Модуль | Владеет | Выставляет | Прячет |
|---|---|---|---|
| `convert` (`src/agent_skill_adapter/convert.py`) | чтением папки скилла, оценкой, сборкой, отчётом | `convert(skill_dir, source, target, *, out=None) -> Conversion` | разбор frontmatter, отображение находок в id записей, подстановки в путях |
| `envspec.gaps` | сравнением описаний | `compare(source, target, bases) -> GapReport` — **существует, не переписывать** | — |
| `envspec.loader` | выбором описания по версии | `select(...)`, `base_specs(...)`, `capability(...)` — **существуют** | — |
| `envspec.model` | схемой описания | `Capability.kind` — закрытый `Literal`; расширяется только сознательно | — |

## Шов для тестов — один

`convert(...)`. Поведение проверяется через него: крошечные описания сред и временная папка
скилла, как это уже сделано в `tests/unit/test_envspec_gaps.py`. Внутренние шаги отдельными
тестами не покрываются — правило сборки видно на выходе `convert`.

## Словарь, общий для всех тасков

- **оценка свойства** — `envspec.gaps.Outcome`: `reproduced` / `missing` / `unknown` / `out-of-scope`.
- **origin** — `envspec.gaps.Origin`: `specification` / `extension`.
- **вывод по файлу и итог запуска** — один `Verdict`: `clean` / `lossy` / `undecidable`.
  Значения `blocked` нет: его не производит ни одна строка таблицы сборки. Появится
  вместе с FR-36, где запрет и определяется.
- **порядок тяжести** — `undecidable` > `lossy` > `clean`. Пустой набор свойств → `clean`.
- **коды возврата, которые производит этот срез** — 0 без потерь, 1 с потерями,
  3 сведений недостаточно, 6 исходные настройки не прочитаны,
  8 столкновение с существующим результатом. Кода 2 здесь нет.

## Что построено законченными тасками

_(дописывается по мере сдачи тасков)_

## Из таска 02 — способность запретить как отдельная запись

- `Capability.kind` расширен до `Literal["skill-field", "subagent-field", "hook-event",
  "hook-decision", "settings-file"]`. Остальные четыре значения не тронуты.
- Новый id записи `hook.decision.block` (вид `hook-decision`) есть в обоих описаниях:
  у Claude Code `supported` (источник `hooks-lifecycle`, где лежат слова «can block it»),
  у Antigravity `unknown` (источник `hooks-config`).
- В `specs/gaps/claude-code-to-antigravity.*` появилась строка
  `hook.decision.block | hook-decision | extension | supported | unknown | unknown`.
- `gaps.compare` не менялся — он безразличен к `kind`, новый вид проходит сравнение сам.
- Заметка `hook.event.PreToolUse` у Claude Code больше не повторяет «can block it»:
  запрет живёт в своей записи, иначе строка отчёта печатала бы его рядом с `reproduced`.

## Из таска 01 — словарь и правило сборки записаны в PRD §5

- Оценка свойства — `envspec.gaps.Outcome`; отдельного словаря для неё нет.
- Вывод по файлу **и** итог запуска — один `Verdict`: `clean` / `lossy` / `undecidable`.
  Значения `blocked` нет до FR-36.
- Происхождение — `specification` / `extension`.
- Таблица сборки (PRD §5.2): `reproduced|out-of-scope` → `clean`/0; `missing` → `lossy`/1;
  `unknown`+`extension` → `lossy`/1; `unknown`+`specification` → `undecidable`/3.
  Порядок тяжести `undecidable` > `lossy` > `clean`; **пустой набор свойств → `clean`**.
- ADR-0006 — переиспользование `Outcome`, со спором с ADR-0003, названным вслух.
- ADR-0007 — почему hooks решаются правкой описания, а не особым правилом в конвертере.

## Из таска 03 — команда `convert`: чтение, оценка, отчёт, код возврата

- `convert(skill_dir, source, target, *, root="specs", out=None, allow_stale=False) -> Conversion`
  — единственный шов. `out` пока не реализован: `NotImplementedError`, не тихая заглушка.
- `Conversion(verdict: Verdict, exit_code: int, report: dict, summary: str)`.
- `verdict_of(outcome, origin) -> Verdict` — таблица сборки PRD §5.2.
  `worst(verdicts)` — пустой набор даёт `clean`. `SEVERITY`,
  `EXIT_CODE = {clean: 0, lossy: 1, undecidable: 3}`, `UNREADABLE = 6`.
- `ConvertError(message, exit_code)`, `Property`, `Finding`,
  `BLOCK = "hook.decision.block"`, `WORKAROUNDS` (выбор по `kind` записи, не ветка),
  `REPORT_SCHEMA = 1`, `REFERENCE`.
- Отчёт: `report_schema, outcome, exit_code, source, target, skill,
  properties[{id, found_as, outcome, origin, verdict, source_says, target_says, note}],
  written, advice, error`. Поле `error` — сверх списка спецификации: без него «отчёт
  выпускается при любом исходе» не говорит машиночитаемо, почему исход такой.
- CLI: `agent-skill-adapter convert SKILL_DIR --source V/E@X --target V/E@X
  [--specs DIR] [--report FILE] [--allow-stale]`. JSON в stdout или в файл,
  человеку — stderr, код возврата из отчёта.
- **Следствие таблицы, важное для таска 04:** папка `references/` в настоящем скилле даёт
  код 3 — открытый стандарт её объявляет, Antigravity молчит (`unknown` + `specification`).

## Из таска 04 — сборка в раскладку Antigravity

- `convert(skill_dir, source, target, *, root="specs", out=None, scope=Scope.PROJECT,
  allow_stale=False) -> Conversion` — `out` реализован, `NotImplementedError` убран.
- `Scope(str, Enum)`: `project` | `user`. `SKILLS_ROOT` / `HOOKS_FILE` — scope → id записи
  `layout`. Константы `SKILL_FILE`, `DIRECTORY`, `EVENT`, `SKILL_NAME`, `WORKSPACE_ROOT`,
  `HOME`, `SKILL_MD`, `HOOKS_KEY`, `COLLISION = 8`.
- `written = [{"from": <что в папке скилла>, "to": <путь назначения из описания цели>,
  "path": <куда легло под out>}]` — третье поле сверх эскиза: у hook и у `--scope user`
  место записи и место назначения разные.
- `advice` получает строку про ручную врезку hook в `.agents/hooks.json`.
- CLI: `agent-skill-adapter convert … [--out DIR] [--scope project|user]`.
- Исход `undecidable` не пишет ничего: переносимая половина скилла выглядела бы
  как собранный скилл и им не является.

## Из таска 05 — отчёт называет пропущенное, отказ не спорит с вердиктом

- `UNWRITABLE = 7` (FR-37): выход за `out` и неудачная запись `--report` больше не уходят
  с кодом 3. Срез производит коды 0, 1, 3, 6, 7, 8.
- `REFUSAL_VERDICT: dict[int, Verdict]` — явное «код отказа → вердикт» вместо обратного
  прохода по `EXIT_CODE`.
- `FRONTMATTER_BYTES = 64 KiB`, `FRONTMATTER_DEPTH = 16`,
  `REQUIRED_FIELDS = ("name", "description")`; `_StrictLoader` отвергает якоря и алиасы
  (FR-15). Отсутствие обязательного поля — код 6 (FR-16).
- `cli.main.SPECS` — абсолютный путь к описаниям репозитория, значение `--specs`
  по умолчанию. Раньше был относительный `specs`, и запуск из чужой папки давал код 3,
  неотличимый от настоящего отказа по `unknown`.
- `properties[].found_as` для id, о котором спросили несколько находок, перечисляет их
  через запятую. `advice` получил строку на каждую папку, которой описание цели
  не даёт места.

## Из таска 06 — тексты и тесты

- Таблица FR-27 получила строку `| 11 | Отчёт не записан туда, куда просили | FR-26 |`,
  резерв стал 12–63; коды 0–10 не тронуты.
- `UNSTOPPED = (EXIT_CODE[Verdict.CLEAN], EXIT_CODE[Verdict.LOSSY])` — коды, поверх которых
  встаёт 11. Код остановки (3, 6, 7, 8) запуск сохраняет.
- Построение id и `_plan` — **как до таска 06**: критерий про читаемый id снят сознательно.
  `lstrip('.')` приравнивал `.scripts/` к `scripts/` и давал либо `FileExistsError` без
  отчёта, либо тихий переезд скрытой папки на документированное место с вердиктом `clean`.
  Двойная точка в `skill.dir..omc` некрасива, поломка дороже.
- Владелец довода про разделение записи — ADR-0007; владелец списка обходов — PRD §5.3;
  остальные места ссылаются.
