window.STATE =
{
  "slug": "env-specs-gate",
  "dir": "2026-09-14-env-specs-gate",
  "title": "Описания сред Claude Code и Antigravity + гейт FR-48",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-14-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "~/.agents/skills/autopilot",
  "startedAt": "2026-09-14T00:07:56+04:00",
  "updatedAt": "2026-09-14T01:11:08+04:00",
  "finishedAt": "2026-09-14T01:11:08+04:00",
  "stages": [
    {
      "id": "preflight",
      "status": "done",
      "startedAt": "2026-09-14T00:07:56+04:00",
      "finishedAt": "2026-09-14T00:09:05+04:00"
    },
    {
      "id": "manifest",
      "status": "done",
      "startedAt": "2026-09-14T00:09:05+04:00",
      "finishedAt": "2026-09-14T00:10:17+04:00"
    },
    {
      "id": "briefing",
      "status": "done",
      "startedAt": "2026-09-14T00:10:17+04:00",
      "finishedAt": "2026-09-14T00:15:42+04:00"
    },
    {
      "id": "spec",
      "status": "done",
      "startedAt": "2026-09-14T00:15:42+04:00",
      "finishedAt": "2026-09-14T00:20:54+04:00"
    },
    {
      "id": "plan",
      "status": "done",
      "startedAt": "2026-09-14T00:20:54+04:00",
      "finishedAt": "2026-09-14T00:23:09+04:00"
    },
    {
      "id": "build",
      "status": "done",
      "startedAt": "2026-09-14T00:23:09+04:00",
      "finishedAt": "2026-09-14T00:55:31+04:00"
    },
    {
      "id": "review",
      "status": "done",
      "startedAt": "2026-09-14T00:28:18+04:00",
      "finishedAt": "2026-09-14T00:55:59+04:00"
    },
    {
      "id": "final",
      "status": "done",
      "startedAt": "2026-09-14T00:55:59+04:00",
      "finishedAt": "2026-09-14T01:11:08+04:00"
    }
  ],
  "requirements": {
    "total": 37,
    "done": 27,
    "inTicket": 0,
    "inSpec": 0,
    "placeholder": 0,
    "deferred": 10,
    "dropped": 0
  },
  "tickets": [
    {
      "id": "01",
      "title": "Форма описания среды, нормализация и хеш",
      "requirements": [
        "R01",
        "R02",
        "R03",
        "R04",
        "R32i",
        "R34i"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        "src/agent_skill_adapter/envspec/"
      ],
      "status": "done",
      "finishedAt": "2026-09-14T00:36:02+04:00",
      "tests": "34 passed",
      "commit": "66723db, 1c39349",
      "startedAt": "2026-09-14T00:23:09+04:00",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0
    },
    {
      "id": "02",
      "title": "Выбор описания по версии и проверка устаревания",
      "requirements": [
        "R05",
        "R08",
        "R17",
        "R22",
        "R29"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/agent_skill_adapter/envspec/loader.py"
      ],
      "status": "done",
      "finishedAt": "2026-09-14T00:38:50+04:00",
      "tests": "42 passed",
      "commit": "6aa89c2",
      "startedAt": "2026-09-14T00:28:18+04:00",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0
    },
    {
      "id": "03",
      "title": "Описание среды Claude Code",
      "requirements": [
        "R03",
        "R05",
        "R21",
        "R26",
        "R28",
        "R33i"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "specs/anthropic/"
      ],
      "status": "done",
      "finishedAt": "2026-09-14T00:46:34+04:00",
      "tests": "load() + 11/11 хешей",
      "commit": "c5cf91c",
      "startedAt": "2026-09-14T00:28:18+04:00",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0
    },
    {
      "id": "04",
      "title": "Описание среды Google Antigravity",
      "requirements": [
        "R03",
        "R05",
        "R21",
        "R26",
        "R27",
        "R33i"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "specs/google/"
      ],
      "status": "done",
      "finishedAt": "2026-09-14T00:49:32+04:00",
      "tests": "load() + 20/20 хешей",
      "commit": "5174d18",
      "startedAt": "2026-09-14T00:28:18+04:00",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0
    },
    {
      "id": "05",
      "title": "Перечень пробелов и критерий продолжения",
      "requirements": [
        "R24",
        "R25",
        "R31"
      ],
      "blockedBy": [
        "02",
        "03",
        "04"
      ],
      "wave": 3,
      "zone": [
        "src/agent_skill_adapter/envspec/gaps.py",
        "specs/gaps/"
      ],
      "status": "done",
      "finishedAt": "2026-09-14T00:55:31+04:00",
      "tests": "57 passed",
      "commit": "59223e1",
      "startedAt": "2026-09-14T00:39:41+04:00",
      "retries": 0,
      "repairs": 3,
      "handoffs": 0
    },
    {
      "id": "06",
      "title": "Сверка с документацией поставщика",
      "requirements": [
        "R12",
        "R13",
        "R14",
        "R15",
        "R19"
      ],
      "blockedBy": [
        "02"
      ],
      "wave": 3,
      "zone": [
        "src/agent_skill_adapter/envspec/freshness.py"
      ],
      "status": "done",
      "finishedAt": "2026-09-14T00:46:09+04:00",
      "tests": "52 passed",
      "commit": "4bbe366",
      "startedAt": "2026-09-14T00:32:12+04:00",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0
    }
  ],
  "singlePass": null,
  "tests": "57 passed",
  "debt": {
    "placeholders": [],
    "assumptions": [],
    "emptyEnv": []
  },
  "additions": [],
  "coverage": {
    "findings": 12,
    "missing": 5,
    "half": 6,
    "extra": 4,
    "acted": "5 дописано в спецификацию (в т.ч. новое требование R35 — структура папок среды), 6 уточнено до однозначности, 1 переформулировано: код возврата перечня пробелов объявлен свойством команды разработчика, а не исходом адаптера по FR-27; 3 «лишних» оставлены — они прикреплены к требованиям R26/R27/R28 манифеста"
  },
  "concerns": [
    {
      "ticket": "03/04",
      "axis": "craft",
      "where": "specs/*.yaml, kind",
      "what": "потолки записаны под kind subagent-field и settings-file, которыми не являются; сопоставление идёт по id и не ломается, но вид записи говорит не то, чем запись является"
    },
    {
      "ticket": "06",
      "axis": "craft",
      "where": "freshness.py:57,66",
      "what": "дата и оба хеша упакованы в свободный текст detail — следующий потребитель достаёт их разбором строки"
    },
    {
      "ticket": "06",
      "axis": "spec",
      "where": "freshness.py:115",
      "what": "повторный прогон дописывает то же расхождение второй раз; при работающем расписании блок растёт линейно"
    },
    {
      "ticket": "03/04",
      "axis": "spec",
      "where": "envspec/model.py Limit.unit",
      "what": "словарь единиц bytes|characters|tokens (из FR-32) не выражает потолок параллельных субагентов (20, Claude Code) и глубину вложенности субагентов (10 уровней, Antigravity) — документированные пределы, которые некуда записать"
    },
    {
      "ticket": "02",
      "axis": "craft",
      "where": "loader.py:140",
      "what": "кривая версия от вызывающего роняет голый ValueError мимо именованных отказов модуля — это граница доверия"
    },
    {
      "ticket": "02",
      "axis": "craft",
      "where": "tests/unit/test_envspec_{core,loader}.py",
      "what": "конструктор валидного описания продублирован в двух файлах тестов"
    },
    {
      "ticket": "02",
      "axis": "craft",
      "where": "tests/unit/test_envspec_loader.py",
      "what": "ветка InvalidSpec на кривом version_range не покрыта ни одним тестом"
    },
    {
      "ticket": "02",
      "axis": "craft",
      "where": "tests/unit/test_envspec_loader.py:171",
      "what": "сетевой скан исключает любой файл с именем freshness.py и ловит только строку import — importlib проходит мимо"
    },
    {
      "ticket": "03",
      "axis": "craft",
      "where": "src/agent_skill_adapter/envspec/model.py",
      "what": "у LayoutEntry нет поля note: hooks — это ключ файла настроек, а не директория, и сказать это данными негде (сказано комментарием в YAML)"
    },
    {
      "ticket": "01",
      "axis": "craft",
      "where": "src/agent_skill_adapter/envspec/normalize.py:11,37",
      "what": "блок кода закрывается любым маркером: ``` внутри ~~~ закрывает его, и заголовки после неё снова считаются заголовками"
    },
    {
      "ticket": "01",
      "axis": "craft",
      "where": "src/agent_skill_adapter/envspec/model.py:35",
      "what": "populate_by_name=True на всей схеме: YAML принимает и from/to, и from_name/to_name, хотя interfaces.md фиксирует одно написание"
    },
    {
      "ticket": "01",
      "axis": "craft",
      "where": "tests/unit/test_envspec_core.py:18-24",
      "what": "шаг NFC в normalize ни одним тестом не покрыт — во всех входах только ASCII"
    }
  ],
  "reviewers": {
    "manifestSpec": null,
    "craft": null
  },
  "blind": {
    "verdict": "две находки, обе воспроизводимы; требования блока A: 7 реализовано, 5 частично, 2 нет (вынесены брифом)",
    "drift": [
      {
        "what": "R12/R13/R14 стояли done — сверка на живом прогоне помечает случайные источники Antigravity недоступными: сайт через раз отдаёт gzip, _fetch декодирует тело как utf-8. С --write это записало бы ложное расхождение в описание цели и по FR-9 вывело бы его из строя",
        "where": "freshness.py:140-147",
        "action": "дозапрос исполнителю таска 06"
      },
      {
        "what": "CI красный: pre-commit hook typos падает на двух намеренных строках тестов (намеренно неверное имя поля в фикстуре и юникодный символ в проверке NFC) — ветка не смержится",
        "where": "tests/unit/test_envspec_core.py:139,167",
        "action": "дозапрос исполнителю таска 01"
      }
    ],
    "partial": [
      "FR-4, FR-5, FR-9 — частично: библиотечная половина есть, флаги и коды возврата принадлежат ядру, вынесенному из прогона",
      "FR-7, FR-8 — частично: скрипт есть, cron и авто-PR отложены ответом заказчика"
    ],
    "note": "ни одна из 95 записей не имеет исхода missing: целевая документация нигде не отказывает словами. Критерий продолжения держится на 73 unknown, из них 8 — записи, которых у цели нет вовсе"
  }
}
