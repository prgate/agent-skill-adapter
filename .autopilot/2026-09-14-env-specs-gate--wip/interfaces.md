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

_(пока пусто)_
