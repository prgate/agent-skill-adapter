# Интерфейсы

Границы решены в спецификации (`spec.md`, раздел «Границы и швы»). Ниже — копия
и правила проекта, которые исполнителю неоткуда вывести. Растёт по мере того,
как таски сдаются: сдавший таск дописывает сюда то, что выставил наружу.

## Правила проекта

- **Рабочая копия:** `.worktrees/antigravity-set`, ветка `feature/asset-set-to-antigravity`.
  Корень репозитория остаётся на `main` и не правится.
- **Стек:** Python 3.10, uv-окружение `.venv`. Зависимости: pydantic, pyyaml, typer, rich;
  dev: pytest, mypy, ruff, pre-commit. **Новая зависимость запрещена** — если таск упирается
  в её отсутствие, он возвращается как `BLOCKED`, а не ставит её.
- **Гейт:** `make check` (ruff, `ruff format --check`, mypy strict по `src tests`, pytest).
  Перед PR — `make pre-commit-run`. Один файл тестов: `uv run pytest tests/unit/test_x.py`.
- **Язык:** код, докстринги, комментарии, документация, сообщения коммитов — по-английски.
  По-русски только `.autopilot/`, `docs/prd/` и русские README.
- **Коммиты:** Conventional Commits, `<type>[(scope)]: <description>`.
- **Что нельзя трогать:** `specs/gaps/` и `specs/schema/` руками — они генерируются
  (`make schema`, команда `gaps`). `AGENTS.md` ≤ 120 строк, `CLAUDE.md`/`GEMINI.md` —
  симлинки на него. Сеть — только из `envspec/freshness.py`.
- **Образец приёмки** — `~/projects/prgate/prgate-kit`. Он **не правится**: это чужой
  репозиторий и образец, а не вход. Ни одно его имя не попадает в код.

## Границы, решённые в спецификации

| Модуль | Владеет | Выставляет | Прячет |
|---|---|---|---|
| `envspec/model.py` | формой описания среды | `Capability.values: list[str] \| None`, `Source.retrieved_from: "web" \| "shipped"` | — (схема закрыта, `extra="forbid"`) |
| `rules.py` | правилами перевода и их версией | `load(path) -> Rules`; `Rules.version`, `Rules.value_of(entry_id, value)`, `Rules.tool_name(name)`, `Rules.ignored(rel)`, `Rules.rewritable(rel)`, `Rules.undocumented` | форму YAML правил |
| `assets.py` | чтением набора с диска | `read(Inputs) -> tuple[Asset, ...]`; `Asset(kind, path, name, frontmatter, findings)` | обход папок, разбор заголовков, применение списка игнорируемого |
| `convert.py` | оценкой, планом и сборкой | `convert(...) -> Conversion` | таблицу вердиктов, раскрытие путей, запись |

## Швы для тестов

Три новых шва, и ни одного сверх них:

1. `rules` — файл правил на входе, выборки на выходе.
2. `assets` — временная папка набора на входе, перечень сущностей на выходе.
3. `convert` — набор против двух крошечных описаний, отчёт на выходе.

Существующие швы `normalize`, `loader`, `gaps`, `freshness` не двигаются.
Внутренние шаги модулей отдельно не тестируются.

## Что выставили сданные таски

<!-- сюда дописывает каждый сданный таск: имя, сигнатура, одна строка «зачем» -->

## Из таска 02 — правила перевода

- `rules.load(path: str | Path) -> Rules` — читает файл правил; кидает `rules.InvalidRules`
- `Rules.version: str` — ключ `rules_version`, версионируется отдельно от описаний сред
- `Rules.value_of(entry_id: str, value: str) -> str | None` — отображение значения поля
- `Rules.tool_name(name: str) -> str | None` — имя инструмента; `None` значит «пары нет»
- `Rules.ignored(rel) -> bool` · `Rules.rewritable(rel) -> bool`
- `Rules.undocumented: Undocumented(action: Literal["copy","skip"], note: str)`
- `rules.TOOL_NAMES_ENTRY = "subagent.frontmatter.tools"` — id, под которым лежат имена
- Файл правил: `rules/claude-code-to-antigravity-1.0.yaml`
- Своей копии этого не пиши: значения и имена переводятся только через `Rules`

## Из таска 01 — описания сред

- `Capability.values: list[str] | None = None` — закрытый набор значений, который называет документация; `None` значит «набора не названо», а не «годится любое»
- `Source.retrieved_from: Literal["web", "shipped"] = "web"`; `freshness.check` пропускает `shipped`
- `EnvSpec.tool_names` и класс `ToolName` **удалены** — отображение имён живёт в файле правил (таск 02)
- В описании Antigravity: источник `skills-shipped-structure` (`retrieved_from: shipped`), запись раскладки `skill.dir.references` на нём, у `subagent.frontmatter.model` объявлены `values: [inherit, flash, pro]`
- Перечень пробелов пересчитан: `skill.dir.references` перешла из `unknown` в `reproduced`

## Из таска 03 — чтение набора

- `assets.read(inputs: Inputs) -> tuple[Asset, ...]` — единственный вход; кидает `assets.ReadError`
- `Inputs(translation: Rules, skills=(), skill=(), agents=(), commands=(), rules=(), plugin: Path | None = None)` —
  `skills`/`agents`/`commands` — папки, `skill` — отдельные папки скиллов (позиционный аргумент),
  `rules` — файлы правил, `plugin` — манифест; `Inputs.named() -> tuple[str, ...]` называет заданные части
- `Asset(kind: Kind, path: Path, name: str, frontmatter: dict[str, Any], findings: tuple[Finding, ...])`;
  **`name == ""` — это сама названная часть, а не сущность: её никуда не переносят**
  (пустая папка, отброшенное по правилам, файл, который никто не объявлял)
- `Kind` — `skill | subagent | command | rules-file | manifest`; вид берётся из опции, а не из имени папки
- `Finding(found_as: str, ids: tuple[str, ...] = (), note: str | None = None)` — `ids` пусты там, где спрашивать
  нечего; тогда строку отчёта несёт `note`
- `frontmatter(path, *, required: Sequence[str] = ()) -> tuple[dict[str, Any], list[str]]` — переехавший из
  `convert._frontmatter` разбор заголовка со всеми отказами (BOM, якорь, дубль ключа, глубина, размер,
  непереносимые значения); вторая половина — строки отчёта о переписанных значениях
- Константы: `REQUIRED_FIELDS`, `SKILL_MD`, `HOOKS_KEY`, `MARKDOWN`, префиксы id (`SKILL_FRONTMATTER`,
  `SKILL_DIR`, `SKILL_TOP`, `SUBAGENT_FRONTMATTER`, `SUBAGENT_BODY`, `COMMAND_FILE`, `RULES_FILE`,
  `PLUGIN_MANIFEST`, `EVENT`, `BLOCK`), тексты `DROPPED` / `UNDECLARED` / `EMPTY`, словарь `PARTS`
- `ReadError` кодов возврата не несёт: их назначает `convert` (чтение не удалось — код 6)
- **Таск 04 обязан снести из `convert.py`** `_findings`, `_frontmatter`, `_portable`, `_StrictLoader`,
  `_Anchored`, `_depth`, `_as_spelled`, `_as_written`, `Finding` и их константы и импортировать их из
  `assets.py`: сейчас это две копии одного разбора заголовка, потому что таск 03 не имел права править `convert.py`
- Дозапрос по 03: отказ остаётся только на путь, который назвал человек (решение §3а). Найденное **внутри**
  названной папки и не похожее на сущность — каталог без `SKILL.md`, файл не того формата, необойдённая
  папка-симлинк — даёт строку (`UNDECLARED` или `LINKED`), а не роняет прогон. Добавлена константа `LINKED`.

## Из таска 04 — сводный отчёт по набору

- `convert(inputs: Inputs, source, target, *, root="specs", out=None, scope=Scope.PROJECT,
  allow_stale=False) -> Conversion` — **первый аргумент теперь состав набора**, а не папка скилла.
  Одна папка скилла = `Inputs(translation=..., skill=(folder,))`; путь раскрывай до абсолютного
  (`os.path.abspath`), иначе папка, названная `.`, приходит без последнего компонента имени
- `Assessed(asset: Asset, name: str, assembled_name: str | None, verdict: Verdict,
  properties: tuple[Property, ...])` — одна сущность набора, уже осуждённая
- `Property.id: str | None` — `None` у строки, которая не спрашивала ни одной записи
  (отброшенное по правилу, необъявленное, папка-симлинк, пустая часть набора)
- `ASKS_NOTHING: dict[str, Outcome]` — что значит строка без записи, по тексту причины из
  `assets` (`DROPPED`/`EMPTY` → `out-of-scope`, `UNDECLARED`/`LINKED` → `unknown`);
  причина не из этой таблицы — это переписанное значение заголовка, и оно идёт в `advice`
- **Формат отчёта — `report_schema: 2`.** Полей `skill` и `properties` наверху больше нет;
  вместо них `assets: [{kind, path, name, assembled_name, verdict, properties: [...]}]`.
  `written`, `advice`, `error` — по-прежнему на верхнем уровне и общие на прогон
- `summary` начинается строкой `the set: <вердикт> (exit N)`, дальше строка на сущность и
  её строки с отступом
- Вердикт прогона — худший по набору (`worst` по вердиктам сущностей); вердикт сущности —
  худший по её строкам плюс `lossy`, если какая-то её часть осталась без места
- Сборка (`--out`) по-прежнему только для скиллов, но план на весь набор проверяется целиком
  одним `_assemble` — столкновение двух скиллов одного набора ловится там же, где столкновение
  двух частей одного скилла
- `cli/main.py` знает `RULES = <repo>/rules/claude-code-to-antigravity-1.0.yaml` (опции состава — таск 08)

### Дозапрос по 04 (репарация)

- Находка без записей **всегда** даёт строку отчёта, чей вердикт считается в `worst`.
  Причина не из `ASKS_NOTHING` → `unknown`/`lossy` с текстом `UNWEIGHED` плюс сама причина;
  советом становится только находка о переписанном значении заголовка, и узнаётся она
  положительно — `REWRITTEN_VALUE = "frontmatter of "` (причина проверяется раньше, чтобы
  файл с таким именем не потерял строку). Потолок назван: у `Finding` нет вида, спросить не у чего
- `_nothing_there(inputs)` в `convert` — до `read`: несуществующий путь из состава даёт отказ
  «нет такого пути» (код 6), а не «нет SKILL.md»; битый симлинк за отсутствующий путь не считается.
  Перечень частей берётся из `assets.PARTS`, своего списка нет
- Второй дозапрос: висячая ссылка и петля ссылок тоже отказ `convert`, а не чтения — названы
  ссылкой и тем, куда она ведёт (`os.readlink`, не `resolve()`: петля из `resolve()` кидает).
  Проверка ссылки идёт раньше `exists()`, который по ссылке ходит и на оба случая отвечает `False`

## Из таска 05 — перевод значений и имён инструментов

- `_translated(asset, target, translation) -> (rows, advice, applied)` в `convert` — приватный,
  но это шов, которым таск 06 будет писать переведённый заголовок: `applied` — список словарей
  `{path, id, from, to, rule}`, готовых к применению к `asset.frontmatter`
- `Assessed.translations: tuple[dict[str, str], ...] = ()` — применённые правила одной сущности;
  применённое правило **не даёт строки** в `properties` (оно ничего не стоило), а даёт запись здесь
- **Отчёт вырос на два верхних поля** (номер `report_schema` прежний, 2): `rules_version` —
  `Rules.version`, и `translations` — плоский список по всему набору
- `FRONTMATTER = {Kind.SKILL: SKILL_FRONTMATTER, Kind.SUBAGENT: SUBAGENT_FRONTMATTER}` — под какими
  id лежат ключи заголовка; вид не из этой таблицы заголовка не несёт, и переводить у него нечего
- Тексты причин, на которые ссылаются тесты: `NO_VALUE_SET` (у цели нет `values` — перевод не
  применяется), `NO_COUNTERPART` (значение вне набора и вне таблицы), `REFUSED_BY_THE_TARGET`
  (правила дают значение, которого нет в наборе цели), `NO_TOOL_COUNTERPART` (имя без пары);
  все четыре — строка `unknown`/`extension` → `lossy`
- Значение не строка там, где перевод применим, — `ConvertError(..., UNREADABLE)`, код 6;
  сообщение называет файл и ключ
- Имена инструментов читаются и строкой через запятую, и YAML-списком (`_tool_names`)
- Решение `opus`/`sonnet` → `pro` записано в `docs/adr/0008-both-source-model-tiers-map-to-pro.md`

### Дозапрос по 05 (репарация)

- **Переведённое значение доезжает до диска.** `_plan(..., translations=entity.translations)`;
  часть `SKILL.md` получает `content=_with_translations(file, applied)` — заголовок правится
  на месте, а не пересобирается через yaml (комментарии, кавычки и порядок ключей чужого
  файла не наши). `_in_the_value_of(header, key, was, became)` меняет слово только внутри
  значения названного ключа: продолжения (строки с отступом) принадлежат последнему открытому
  ключу, граница слова не даёт `sonnet` внутри `sonnet-2.0` превратиться в `pro`
- `_Part.content` теперь ставится **рядом** с `copied_from`, а не вместо: байты берутся из
  `content`, а `copied_from` по-прежнему отвечает на вопрос «а это была ссылка?» (`_links_within`)
- Ключ берётся как последний шаг id (`rule["id"].rpartition(".")[2]`) — таблицы пар нет
- Сборка субагентов по-прежнему не сделана (таск 06): для них `applied` пока только в отчёте

## Из таска 06 — назначения для всего набора

- `ROOT_ENTRY: dict[Kind, dict[Scope, str]]` в `convert` — под каким id раскладки лежит корень
  для каждого вида: `skills.*`, `agents.*`, и `rules.project` **на обоих уровнях** (решение
  пользователя «всегда `.agents/rules/`»). Вида нет в таблице — он не собирается никуда
- `Assessed.assembled_name` теперь не только про скилл: у субагента и файла правил это имя
  файла на диске (`asset.path.name`), без суффикса среды; `None`, если у цели нет корня
- `_plan(entity, out, target, scope, translation, *, skills_root)` — диспетчер по виду;
  прежний `_plan` стал `_plan_skill` с той же сигнатурой
- `CONTENT = {Kind.SUBAGENT: _with_translations, Kind.RULES: _with_trigger}` — чем переписан
  единственный файл сущности по дороге; вида нет в таблице — копируется байт в байт
- `TRIGGER_ENTRY = "rules.frontmatter.trigger"`, `NOTHING_WRITTEN = ""` — id записи и то, как
  файл правил без заголовка выглядит слева в паре правил перевода. `_trigger(asset, target,
  translation) -> (rows, applied)`; `_declares(path, key)`, `_header_of(text)`,
  `_with_trigger(path, applied)`
- `NO_ROOM_FOR: dict[Kind, str]` — текст строки отказа вместо `UNDECLARED`; сегодня только
  `Kind.COMMAND`. `_judge(...)` принял шестым аргументом `kind`
- `_nowhere(target, kind, scope)` — строка «у цели нет корня для этого вида» плюс `lossy`;
  отказом прогона это не становится (иначе теряется всё остальное в наборе)
- `_undocumented(entity, out, target, scope, translation)` — исполняет `action: copy|skip`:
  при `copy` путь, который никто не объявлял, кладётся в корень своего вида под своим именем
- В описании Antigravity: источник `rules-shipped-trigger` (`retrieved_from: shipped`,
  `SKILL.md` скилла `agy-customizations`, якорь `Progressive Disclosure (Skills and Rules)`)
  и запись `rules.frontmatter.trigger` с `values: [always_on, model_decision]`.
  `kind: settings-file` — ближайший из закрытого `Literal` в `model.py`, править который
  таску запрещено; для поля файла правил вида в схеме нет
- В файле правил перевода добавлена пара `rules.frontmatter.trigger: {"": always_on}`;
  `rules_version` остался `1.0` (номер стоит и в имени файла, которое знает `cli/main.py`)

### Дозапрос по 06 (репарация)

- `_text_of(path) -> str` — единственное чтение чужого файла в `convert`: не-UTF-8 даёт
  `ConvertError(..., UNREADABLE)` с путём (код 6), а не `UnicodeDecodeError` трассировкой.
  `UnicodeDecodeError` — это `ValueError`, и внешний перехват `convert` его не ловил
- `_undocumented(entity, out, translation) -> (parts, advice)` — корня цели больше не
  спрашивает: необъявленное кладётся под `--out` по `<имя названной части>/<путь внутри неё>`
  и **никогда** в корень, который среда сканирует на сущности (`STAGED_NOT_PLACED`).
  Иначе папка без `SKILL.md` уезжала в `.agents/skills/` и читалась средой как битый скилл
- `_skills_root` удалён. Отсутствие `skills.*` или `skill.file` — такая же строка `_nowhere`
  плюс `lossy`, как у субагента: прежний отказ кодом 3 звался до цикла оценки и оставлял
  `assessed` пустым, теряя строки всего остального набора. `_nowhere` для `Kind.SKILL`
  спрашивает обе записи (корень папки и имя файла внутри неё), для прочих видов — одну
- `_plan(entity, out, target, scope, translation)` — параметра `skills_root` больше нет,
  корень читается из `ROOT_ENTRY` внутри

## Из таска 07 — подстановка ссылок

- `_relinked(parts, inputs) -> (parts, links, advice)` — зовётся после того, как план собран по
  всему набору, и до записи: адрес переписывается против того, куда лёг названный файл, а это
  известно только когда план целый. Берёт `part.content`, если он уже поставлен, — поэтому
  перевод значений и подстановка ссылок не дерутся за один файл
- Поле отчёта `links: [{path, from, to}]` — рядом с `translations`, по записи на применённую
  подстановку; в сводке строка `pointed <было> at <стало> in <путь>`
- `OUT_OF_THE_SET` — строка про адрес, ведущий наружу набора
- Адрес ищется в двух формах: Markdown-ссылка `](…)` и инлайн-код в обратных кавычках
- Переписывается только адрес на файл, который **этот же прогон** переместил; файл, оставшийся
  на месте, не трогается; перечень файлов, которые вообще можно править, даёт `Rules.rewritable`
- `docs/adr/0009` — почему перенесённый файл правил получает `trigger: always_on`

## Из таска 08 — состав из командной строки и установка в живой корень

- Команда взяла состав: `--skills DIR`, `--agents DIR`, `--commands DIR`, `--rules PATH` — повторяемые,
  `--plugin FILE` — одна, позиционный аргумент остался одной папкой скилла и стал необязательным.
  Все пути раскрываются до абсолютных в `cli/main.py::_absolute`
- `--translation PATH` — файл правил перевода; `RULES` остался значением по умолчанию. Файл, который
  не читается или не проходит схему, даёт отчёт с кодом 6, а не трассировку (`rules.InvalidRules` и
  `OSError` ловятся в CLI)
- `convert(..., install: bool = False)` — пишет в живые корни цели вместо `--out`; вместе с `--out`
  отказ кодом 7 (`UNWRITABLE`) до первого чтения. Без `install` и без `out` по-прежнему не пишется ничего
- `convert.refusal(source, target, exit_code, message) -> Conversion` — отчёт и сводка для того,
  что не дало прогону начаться (сегодня только нечитаемые правила перевода); `rules_version` пуст
- `_Where(out: Path | None)` в `convert` — `None` значит «живые корни». `_Where.place(root, inside,
  skill_name) -> (назначение, что пишем, под чем должно остаться)`; `_live(template, skill_name)`
  раскрывает `~` в домашнюю папку, `<workspace-root>` и голый путь — в текущую папку
- `_Part.root: Path` — корень, за который часть не выходит: `out` у сборки, корень раскладки у установки.
  `_assemble(parts)` больше не берёт `out` — проверки «не вышло за корень» и «не легло на сам корень»
  идут по `part.root`; `_links_on_the_way(root, staged)` переименовал параметр
- `_announced(parts)` — план в `sys.stderr` до первой записи, только при установке; занятое место
  помечено `ALREADY THERE`. Повторная установка печатает план и отказывает кодом 8, не трогая файлы
- `INSTALL_WITH` — строка совета у каждого прогона с `--out`, который что-то собрал: как установить
- При установке **не пишутся** две вещи, у которых нет корня в раскладке: необъявленные пути
  (`NOWHERE_TO_STAGE`) и заготовка hooks-записи — обе становятся строкой совета

### Дозапрос по 08 (репарация)

- `ASKS_ITS_PLACE = {Kind.RULES: RULES_FILE}` и `_about_its_place(entry_id, kind, scope)` в `convert`:
  файл правил спрашивает id **места** (`ROOT_ENTRY[Kind.RULES][scope]` → `rules.project`), а не
  `rules.file`, которого нет ни в одном описании. Строка выходит `reproduced`/`extension` через
  `_target_alone` (цель называет запись раскладки) — чистый перенос набора с файлом правил даёт код 0
- `_judge(..., kind, scope)` — шестым аргументом уровень; больше ничего в подписи не двинулось
- Команда в таблицу не входит намеренно: у цели нет корня для команд, и `command.file` без ответа —
  это и есть честный ответ про неё
- `_live(template, skill_name) -> (место, корень)` — корень установки это **домашняя папка или
  рабочая**, и никогда сам раскрытый путь: раскладочный путь, начинающийся со слэша, меряется
  от рабочей папки, оказывается вне обоих корней и получает тот же отказ (код 7), что при `--out`.
  Раньше он приходил и назначением, и собственным корнем — проверка была истинна по построению
- `destinations_tree(tmp_path, agents_root=".agents/agents/")` в тестах — второй аргумент нужен
  тесту про путь, ведущий из обоих корней
