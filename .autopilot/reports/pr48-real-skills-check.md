# PR #48 на реальных скиллах — отчёт проверки

- Дата: 2026-09-14
- Ветка: `feature/agentskills-baseline` (PR #48)
- Рабочее место: worktree `.worktrees/baseline`
- Проверка первая: коммит `753e611`. Найдены два дефекта, оба починены в этом же PR —
  раздел «Что починено».

## Что проверялось

Взяты два живых набора скиллов и сопоставлены с закоммиченными описаниями сред:

| набор | коммит клона | скиллов (SKILL.md) |
|---|---|---|
| `github.com/mattpocock/skills` | `--depth 1` от 2026-09-14 | 37 |
| `github.com/obra/superpowers` | `--depth 1` от 2026-09-14 | 14 |

Скрипт `pr48-real-skills-probe.py` вытаскивает из каждого скилла frontmatter-ключи,
бандл-директории и события хуков, переводит их в id записей описания и спрашивает
оба описания плюс `outcome`/`origin` из `specs/gaps/claude-code-to-antigravity.json`.

Запуск (из worktree):

```bash
mkdir -p /tmp/skill-clones && cd /tmp/skill-clones
git clone --depth 1 https://github.com/mattpocock/skills.git mattpocock-skills
git clone --depth 1 https://github.com/obra/superpowers.git superpowers
cd -  # обратно в worktree
uv run python .autopilot/reports/pr48-real-skills-probe.py /tmp/skill-clones
```

Директория с клонами — первый аргумент; имена подкаталогов
(`mattpocock-skills`, `superpowers`) скрипт ждёт именно такими. Сети требуют только
клоны — сам скрипт читает файлы и закоммиченные описания.

Проверка остаётся ручной и в CI не входит: клоны требуют сети, а вкоммитить 51 чужой
SKILL.md — это тащить в репозиторий чужой код с чужими лицензиями. Ценность прогона
разовая (валидация описаний против живых данных), регрессию он не стережёт.

## Результат: описание Claude Code выдержало

| фича из реальных скиллов | скиллов | claude-code | antigravity | outcome | origin |
|---|---|---|---|---|---|
| `skill.frontmatter.name` | 51 | supported | supported | reproduced | specification |
| `skill.frontmatter.description` | 51 | supported | supported | reproduced | specification |
| `skill.frontmatter.disable-model-invocation` | 22 | supported | unknown | unknown | extension |
| `skill.dir.scripts` | 4 | inherited | documented | reproduced | specification |
| `skill.frontmatter.argument-hint` | 4 | supported | unknown | unknown | extension |
| `skill.dir.references` | 1 | inherited | — | unknown | specification |
| `skill.dir.examples` | 1 | — | documented | — | — |
| `hook.event.SessionStart` | 1 (плагин superpowers) | supported | unknown | unknown | extension |

`inherited` — запись открытого стандарта: описание Claude Code её не повторяет, но
отвечает за неё, объявив `extends`. `documented` — layout-запись: у места нет значения
`support`, назвать место и есть всё утверждение.

- Ни одного frontmatter-ключа вне описания: 20 полей `skill.frontmatter.*` в
  `claude-code-2.1.yaml` покрывают 100% реального употребления.
- Разделение specification/extension из PR ложится на живые данные ровно: то, что
  переживает перенос — поля открытого стандарта; всё, что повисает в `unknown` —
  надстройка Claude Code.
- Лимиты держатся: 0 нарушений `name` >64, `description` >1024, listing >1536.
  Самое длинное описание — 417 символов (`mattpocock-skills/code-review`).
- Практический вывод: **27 из 51 скилла** цепляют то, что Antigravity не документирует.

## Что починено

Первый прогон нашёл два дефекта, оба про один класс — «что стандарт определяет про сам
файл скилла»; он проваливался между базовым описанием и целевым.

### Дефект 1: `extends` наследовал ярлык, а не участников сравнения

`compare()` шёл по `source.capabilities` и `source.layout` — по спискам одного лишь
Claude Code, а `is_inherited()` использовался только для колонки origin. Записи, которые
есть только в базе, в отчёт не попадали вовсе: ровно 95 записей = 79 capabilities +
16 layout `claude-code-2.1.yaml`.

Починка (`envspec/gaps.py`): `compare()` берёт записи базы, которых нет в описании
источника, как полноправные source-записи. Основание — сам `extends`: объявив, что
реализует формат, среда отвечает за всё, что формат определяет, повторено это в её
описании или нет. Подтянутая запись несёт `support` базы («формат это определяет») и
сравнивается с целью как своя.

В отчёт добавились 7 записей: `skill.file.format`, `skill.body.content`,
`skill.body.file-references`, `skill.file`, `skill.dir.scripts`, `skill.dir.references`,
`skill.dir.assets`.

### Дефект 2: асимметрия id — одно и то же названо по-разному

`antigravity-2.0.yaml` объявлял `skill.file.name` и `skill.bundled-resources` как
capabilities, а база выражает то же самое как layout `skill.file` и `skill.dir.*`.
Сопоставление идёт по id **внутри своего списка**, поэтому спарить их было нельзя:
`skill.bundled-resources` лежал в файле мёртвым грузом, хотя это единственное место, где
цель прямо говорит «бандлы поддерживаю». Переименования на месте не хватило бы — записи
должны были переехать из `capabilities` в `layout`.

Починка (`specs/google/antigravity-2.0.yaml`), по документации Antigravity:

- `skill.file.name` → layout `skill.file` (`<skill-name>/SKILL.md`);
- `skill.bundled-resources` → layout `skill.dir.scripts` (`<skill-name>/scripts/`) плюс
  собственные `skill.dir.examples`, `skill.dir.resources` — Antigravity рисует
  `examples/` и `resources/`, а не `references/` и `assets/` стандарта. Разные имена —
  разные места; прочитать одно как другое значило бы записать цели воспроизведение того,
  чего она не писала. Поэтому `skill.dir.references` и `skill.dir.assets` остаются
  `unknown`;
- добавлены capabilities `skill.file.format` и `skill.body.content` с новым источником
  `skills-creating` (секция «Creating a skill»): страница прямо говорит «Every skill
  needs a `SKILL.md` file with YAML frontmatter at the top» и что тело держит инструкции.
  Без этих записей отчёт показал бы ложный `unknown` там, где цель документирует;
- `skill.body.file-references` записи не получил: про относительные ссылки из `SKILL.md`
  и их глубину документация Antigravity не говорит ничего.

### Что изменилось в перечне

| | было (`753e611`) | стало |
|---|---|---|
| записей | 95 | 102 |
| воспроизводится | 22 (2 по стандарту) | 26 (6) |
| не поддерживает | 0 | 0 |
| неизвестно | 70 (1 по стандарту, 8 нет записи у цели) | 73 (4, 11) |
| вне переноса | 3 | 3 |

Проверка после починки: `skill.dir.scripts` и `skill.dir.references` больше не
показывают «—» в колонках outcome/origin. `make check` и `make pre-commit-run` зелёные,
README (RU/EN) приведён к новым числам.

## Мелочи, не дефекты

- `<skill>/agents/openai.yaml` — во всех 37 скиллах mattpocock. Упаковка под
  Codex/OpenAI внутри директории скилла: третья среда, вне рамок обоих описаний.
- `superpowers/hooks/hooks-cursor.json` использует `sessionStart` в нижнем
  регистре — Cursor, тоже вне рамок.
- `hooks.plugin` → reproduced: файл `plugins/<name>/hooks.json` у Antigravity есть,
  а событие `SessionStart` — unknown. Плагин доедет, хук под вопросом; отчёт
  показывает это корректно двумя разными записями.
- `superpowers/writing-skills` везёт `examples/` — директорию, которой стандарт не
  определяет, а Antigravity определяет. Обратная сторона того же класса: перенос в
  Antigravity её донесёт, но сказать это можно только про цель, не про источник.
