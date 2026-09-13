# Интерфейсы прогона

Файл читает каждый субагент до того, как напишет строку кода.

## Правила проекта

- **Стек:** Python ≥ 3.10, uv, pytest, ruff, mypy strict. Пакет — `src/agent_skill_adapter/`.
- **Команды:** `make check` (ruff + mypy + pytest), `make test`, `make lint`, `make format`.
- **Язык артефактов репозитория — английский**: код, докстринги, комментарии, коммиты, документация.
  Файлы `.autopilot/` — исключение, они на русском (это переписка с заказчиком).
- **Новых сторонних зависимостей не добавлять.** Уже объявлены и доступны: `pydantic>=2`, `pyyaml`,
  `typer`, `rich`. Модель и проверка схемы описания — на `pydantic`, чтения YAML — на `pyyaml`.
  Нужна ещё одна библиотека — верни `BLOCKED`, не ставь. (CFP §4, уровень 3.)
- **Не трогать:** `docs/`, `AGENTS.md`, `CLAUDE.md`, `.autopilot/`, `pyproject.toml` —
  `pyproject.toml` менять не нужно: всё требуемое уже в зависимостях.
- **Тесты:** по правилу репозитория (AGENTS.md §7) тест пишется там, где он может упасть от
  неверного поведения: разбор формата, вычисление, ветвление, граница доверия. Не тестировать
  существование файла, заголовок в документе, константу.
- **Сеть:** только модуль `envspec.freshness`. Любой другой модуль, импортирующий `urllib`/`requests`, —
  дефект. Тесты сети не касаются: `freshness` принимает функцию `fetch` параметром.

## Границы, решённые в спецификации

| Модуль | Владеет | Выставляет | Прячет |
|---|---|---|---|
| `envspec.normalize` | правилом нормализации и хешированием | `section_text(markdown, anchor) -> str`, `normalize(text) -> str`, `digest(text) -> str` | разбор markdown, порядок шагов нормализации |
| `envspec.model` | формой описания среды | `EnvSpec`, `Capability`, `Source`, `Limit`, `ToolName`, `InvisibleSource`, `Discrepancy`, `Support` | сериализацию YAML |
| `envspec.loader` | чтением, проверкой схемы, выбором по версии, устареванием | `load(path)`, `load_all(root)`, `select(root, vendor, environment, version)`, `is_stale(spec, today)` | сравнение версий, поиск файлов |
| `envspec.gaps` | сравнением двух описаний | `compare(source, target) -> GapReport`, `render_markdown(report)`, `render_json(report)` | правило сопоставления записей |
| `envspec.freshness` | сверкой с документацией поставщика (единственный сетевой модуль) | `check(spec, fetch=...) -> list[Discrepancy]`, `record(path, discrepancies)` | HTTP, заголовки, повторы |

**Швы для тестов — два:** `envspec.loader` (чтение → выбор → устаревание) и
`envspec.normalize` (текст → хеш). `gaps` проверяется через `compare` на двух маленьких
описаниях, `freshness` — через подставленную `fetch`.

## Что построено (дописывают таски по мере сдачи)

### Из таска 01 — форма описания, нормализация, чтение

- `envspec.normalize.section_text(markdown: str, anchor: str) -> str` — раздел по якорю;
  `AnchorError(ValueError)` — якорь не найден или неоднозначен. Заголовки внутри ``` / ~~~
  заголовками не считаются.
- `envspec.normalize.normalize(text: str) -> str`, `envspec.normalize.digest(text: str) -> str`.
  `digest` нормализует вход сам — отдельно `normalize` перед ним звать не нужно.
- `envspec.model`: `Support`, `DiscrepancyKind` (`changed` | `unreachable`), `Source`, `Capability`,
  `LayoutEntry`, `Limit`, `ToolName` (в YAML поля `from`/`to`, в Python — `from_name`/`to_name`),
  `InvisibleSource`, `Discrepancy`, `EnvSpec`.
- `EnvSpec`: `schema_version`, `vendor`, `environment`, `version_range`, `checked_at: date`,
  `stale_after_days` (по умолчанию 30), `normalization: Literal["v1"]`, `sources`, `capabilities`,
  `layout`, `limits`, `tool_names`, `invisible_sources`, `discrepancies`. Схема закрытая
  (`extra="forbid"`): неизвестное поле — ошибка.
- `envspec.loader.load(path) -> EnvSpec`; все схемные отказы — `InvalidSpec(ValueError)`
  с путём файла в сообщении.
- `sha256` источника проверяется шаблоном `^[0-9a-f]{64}$`.
- Тесты: `make check` (ruff + mypy strict + pytest), один файл — `uv run pytest <путь>`.

### Из таска 02 — выбор описания по версии и устаревание

- `envspec.loader.load_all(root) -> list[EnvSpec]` — все описания из дерева `root`, файлы `*.yaml`.
- `envspec.loader.select(root, vendor, environment, version, *, allow_stale=False, today=None) -> EnvSpec`.
  `SpecNotFound` — ни одного подходящего (в сообщении версия и все диапазоны);
  `AmbiguousSpec` — несколько (перечислены пути); `StaleSpec` — описание устарело.
- `envspec.loader.is_stale(spec, today) -> bool`; `envspec.loader.capability(spec, id) -> Support`
  (функция, не метод `EnvSpec`).
- Сравнение версий своё: точечные числовые версии, операторы `>= <= > < == !=`. Pre-release
  не поддерживается. Кривой `version_range` — `InvalidSpec` уже на `load()` (проверка формы в `model.py`).
  Неразбираемая **запрошенная** версия — `InvalidVersion(ValueError)`.
- Правило «сеть только во `freshness`» закреплено тестом, который сканирует `src/**.py`.

### Из таска 03 — описание Claude Code

- `specs/anthropic/claude-code-2.1.yaml`. `version_range: ">=2.1.0,<2.2.0"`, `normalization: v1`,
  `checked_at: 2026-09-14`, `environment_version: 2.1.270`.
- 76 записей: `skill-field` 20, `subagent-field` 17, `hook-event` 33, `settings-file` 6.
  По поддержке: 73 `supported`, 3 `unsupported` (`license`, `compatibility`, `metadata` — документация
  говорит, что поле принимается и не действует). 8 источников, все хеши пересчитаны от живых страниц.
- Плюс `layout` 16, `limits` 4, `invisible_sources` 5, `discrepancies: []`.
- Идентификаторы записей этого файла — то, по чему таск 05 ищет соответствие в описании Antigravity.

### Из таска 06 — сверка с документацией поставщика

- `envspec.freshness.Fetch = Callable[[str], str]` — возвращает текст страницы или бросает;
  не-200 обязан бросать.
- `envspec.freshness.markdown_url(source) -> str` — `source.markdown_url` либо `f"{source.url}.md"`.
- `envspec.freshness.check(spec, *, fetch, today=None) -> list[Discrepancy]`.
- `envspec.freshness.record(path, discrepancies) -> None` — текстовая правка только блока
  `discrepancies:`, остальной YAML байт-в-байт прежний.
- `envspec.freshness.main(argv=None, *, fetch=_fetch) -> int` — `python -m agent_skill_adapter.envspec.freshness
  [--root specs] [--write]`. На найденных расхождениях возвращает 0 (коды возврата закреплены FR-27
  за ядром); несуществующий или пустой корень — `parser.error`, код 2.
- `unreachable` возникает только от `(OSError, UnicodeDecodeError, AnchorError)`; дефект нашего кода
  всплывает наружу, а не уезжает в файл описания расхождением.
- `USER_AGENT = "Mozilla/5.0"` — тот же, что в тасках 03–04.
- Это единственный модуль проекта, которому разрешена сеть; тест в `test_envspec_loader.py`
  это стережёт по конкретному пути файла.

### Из таска 04 — описание Google Antigravity

- `specs/google/antigravity-2.0.yaml`. `version_range: ">=2.0.0,<3.0.0"`, `environment_version: "2.0"`
  (номера сборки Antigravity не публикует).
- 93 записи: `hook-event` 35, `subagent-field` 24, `skill-field` 22, `settings-file` 12.
  По поддержке: 27 `supported`, 66 `unknown`, 0 `unsupported` — документация Antigravity нигде
  не отрицает возможность словами, поэтому `unsupported` не появился честно.
  У всех записей описания Claude Code здесь есть пара.
- 20 источников, все хеши пересчитаны от живых страниц, источников-сирот нет.
- `layout` 15 записей, из них 8 идентификаторов общие с описанием Claude Code — по ним и идёт
  сопоставление в таске 05. `limits` 1 (`rules.file.size`, 12000 characters).
- `agent-memory.project` / `agent-memory.user` Claude Code пары здесь не имеют вовсе: у Antigravity
  такого понятия в документации нет. Это честный пробел, а не расхождение имён.
- `tool_names` **пуст**: документация Antigravity нигде не сопоставляет имена инструментов
  Claude Code со своими. Пара `Read`→`view_file` была бы нашей догадкой, а не данными.
  Отсутствие таблицы записано записью `agent.tool-names.mapping` со `support: unknown`, чтобы
  в перечень пробелов оно попало результатом, а не пустой строкой.

### Из таска 05 — перечень пробелов

- `envspec.gaps.Outcome` (`reproduced` | `missing` | `unknown`), `Gap`, `GapReport`
  (`.count(outcome)`, `.transferable`).
- `compare(source, target) -> GapReport`, `render_markdown(report) -> str`, `render_json(report) -> str`.
- `main(argv=None) -> int` — `python -m agent_skill_adapter.envspec.gaps [--root specs] [--out specs/gaps]`.
  Пустой перечень (нечего переносить) — код 1 и прямое сообщение.
- `SOURCE = ("anthropic", "claude-code")`, `TARGET = ("google", "antigravity")`.
- В сопоставление идут `capabilities` и `layout`; `limits` и `invisible_sources` — нет
  (идентификаторы не пересекаются, а невидимые источники — свойство исходной среды).
- **Перечень пересобирается после любой правки описаний.** Файлы `specs/gaps/*` — производные.
