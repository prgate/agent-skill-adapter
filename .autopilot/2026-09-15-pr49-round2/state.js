window.STATE =
{
  "slug": "pr49-round2",
  "dir": "2026-09-15-pr49-round2",
  "title": "Второй круг ревью PR #49: молчаливая потеря значения",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T1",
  "briefFile": "2026-09-15-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "~/.agents/skills/autopilot",
  "startedAt": "2026-09-15T10:00:00+04:00",
  "updatedAt": "2026-09-15T14:40:00+04:00",
  "finishedAt": "2026-09-15T14:40:00+04:00",
  "stages": [
    { "id": "preflight", "status": "done", "startedAt": "2026-09-15T10:00:00+04:00", "finishedAt": "2026-09-15T10:02:00+04:00" },
    { "id": "manifest",  "status": "done", "startedAt": "2026-09-15T10:02:00+04:00", "finishedAt": "2026-09-15T10:04:00+04:00" },
    { "id": "briefing",  "status": "skipped", "note": "вопросов не потребовалось — задача целиком из опубликованного ревью" },
    { "id": "spec",      "status": "done", "startedAt": "2026-09-15T10:04:00+04:00", "finishedAt": "2026-09-15T10:12:00+04:00" },
    { "id": "plan",      "status": "done", "startedAt": "2026-09-15T10:12:00+04:00", "finishedAt": "2026-09-15T10:15:00+04:00" },
    { "id": "build",     "status": "done", "startedAt": "2026-09-15T10:15:00+04:00", "finishedAt": "2026-09-15T14:35:00+04:00" },
    { "id": "review",    "status": "done", "startedAt": "2026-09-15T13:00:00+04:00", "finishedAt": "2026-09-15T14:35:00+04:00" },
    { "id": "final",     "status": "done", "startedAt": "2026-09-15T14:35:00+04:00", "finishedAt": "2026-09-15T14:40:00+04:00" }
  ],
  "requirements": { "total": 9, "done": 9, "inTicket": 0, "inSpec": 0, "placeholder": 0, "deferred": 0, "dropped": 0 },
  "tickets": [
    { "id": "01", "startedAt": "2026-09-15T10:15:00+04:00", "title": "Побеждает последний: два места, где значение исчезает молча",
      "requirements": ["R01","R02","R03","R04","R05","R07i","R09i"],
      "blockedBy": [], "wave": 1, "zone": ["src/agent_skill_adapter/convert.py","tests/unit/"], "status": "done", "finishedAt": "2026-09-15T13:40:00+04:00", "tests": "make check -> 134 passed", "commit": "87926ad",
      "retries": 0, "repairs": 2, "handoffs": 0 },
    { "id": "02", "startedAt": "2026-09-15T13:42:00+04:00", "title": "Вердикт не зависит от того, попросили ли байты",
      "requirements": ["R07i"],
      "blockedBy": ["01"], "wave": 2, "zone": ["src/agent_skill_adapter/convert.py","tests/unit/"], "status": "done", "finishedAt": "2026-09-15T14:35:00+04:00", "tests": "make check -> 139 passed", "commit": "87926ad",
      "retries": 0, "repairs": 2, "handoffs": 0 }
  ],
  "singlePass": null,
  "tests": "make check -> 139 passed (было 127 на старте круга); make pre-commit-run -> 15 хуков Passed; 38 настоящих скиллов — 12/6/17/3 с флагом и без",
  "debt": { "placeholders": [], "assumptions": [], "emptyEnv": [] },
  "additions": [],
  "coverage": null,
  "concerns": [
    { "from": "третий круг ревью", "axis": "craft", "where": "tests/unit/test_convert.py (петля ссылок)",
      "what": "тест закрепляет исход (код 7, отчёт, ноль трассировок), а не механизм: на Python 3.10–3.12 отказ приходит из RuntimeError в resolve(), на 3.13+ — из OSError ELOOP в mkdir",
      "condition": "выбор осознанный: закрепить механизм значило бы сделать тест красным на интерпретаторе, который requires-python разрешает. Пока гейт на 3.10, `_resolved` закреплён; если гейт переедет на 3.13, тест останется зелёным и перестанет его держать" },
    { "from": "01", "axis": "manifest", "where": "convert.py (хвост `..` в layout)", "status": "закрыто таском 02",
      "what": "таск 01 открыл дыру: формы `x/../..` и `a/b/../../..` записывали SKILL.md за пределы --out с кодом 0",
      "condition": "установлено сравнением трёх состояний; таск 02 закрыл, все пять форм дают 7" }
  ],
  "reviewers": { "manifestSpec": "rev2-manifest", "craft": "rev2-craft" },
  "blind": { "ran": null, "skipped": "прогон целиком из находок внешнего ревью PR #49 — оно и есть независимая проверка; обе оси перепроверяли каждую правку запуском, включая восстановление предыдущих состояний кода для сравнения" }
}
