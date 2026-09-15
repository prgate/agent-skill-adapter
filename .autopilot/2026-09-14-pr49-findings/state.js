window.STATE =
{
  "slug": "pr49-findings",
  "dir": "2026-09-14-pr49-findings",
  "title": "Находки ревью PR #49: отчёт при любом исходе",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T1",
  "briefFile": "2026-09-14-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "~/.agents/skills/autopilot",
  "startedAt": "2026-09-14T22:58:18+04:00",
  "updatedAt": "2026-09-15T01:28:00+04:00",
  "finishedAt": "2026-09-15T01:28:00+04:00",
  "stages": [
    { "id": "preflight", "status": "done", "startedAt": "2026-09-14T22:58:18+04:00", "finishedAt": "2026-09-14T23:02:00+04:00" },
    { "id": "manifest",  "status": "done", "startedAt": "2026-09-14T23:02:00+04:00", "finishedAt": "2026-09-14T23:04:00+04:00" },
    { "id": "briefing",  "status": "done", "startedAt": "2026-09-14T23:04:00+04:00", "finishedAt": "2026-09-14T23:10:00+04:00" },
    { "id": "spec",      "status": "done", "startedAt": "2026-09-14T23:10:00+04:00", "finishedAt": "2026-09-14T23:16:00+04:00" },
    { "id": "plan",      "status": "done", "startedAt": "2026-09-14T23:16:00+04:00", "finishedAt": "2026-09-14T23:20:00+04:00" },
    { "id": "build",     "status": "done", "startedAt": "2026-09-14T23:20:00+04:00", "finishedAt": "2026-09-15T01:25:00+04:00" },
    { "id": "review",    "status": "done", "startedAt": "2026-09-14T23:34:00+04:00", "finishedAt": "2026-09-15T01:25:00+04:00" },
    { "id": "final",     "status": "done", "startedAt": "2026-09-15T01:25:00+04:00", "finishedAt": "2026-09-15T01:28:00+04:00" }
  ],
  "requirements": {
    "total": 14, "done": 14, "inTicket": 0, "inSpec": 0,
    "placeholder": 0, "deferred": 0, "dropped": 0
  },
  "tickets": [
    { "id": "01", "startedAt": "2026-09-14T23:20:00+04:00", "title": "Граница отказа: отчёт при любом исходе",
      "requirements": ["R01","R02","R02.1","R03","R04","R09","R11","R14i"],
      "blockedBy": [], "wave": 1, "zone": ["src/agent_skill_adapter/convert.py","tests/unit/","docs/prd/"], "status": "done", "finishedAt": "2026-09-15T01:00:00+04:00", "tests": "make check -> 123 passed", "commit": "37c5295",
      "retries": 0, "repairs": 2, "handoffs": 0 },
    { "id": "02", "startedAt": "2026-09-14T23:20:00+04:00", "title": "Тексты и политика языка",
      "requirements": ["R05","R06","R07","R08","R10"],
      "blockedBy": [], "wave": 1, "zone": ["AGENTS.md",".autopilot/"], "status": "done", "finishedAt": "2026-09-15T00:20:00+04:00", "tests": "make check -> 118 passed", "commit": "bf02b33",
      "retries": 0, "repairs": 1, "handoffs": 0 },
    { "id": "03", "startedAt": "2026-09-15T01:00:00+04:00", "title": "Три значения float, которых в JSON нет",
      "requirements": ["R03"],
      "blockedBy": ["01"], "wave": 2, "zone": ["src/agent_skill_adapter/convert.py","tests/unit/"], "status": "done", "finishedAt": "2026-09-15T01:25:00+04:00", "tests": "make check -> 127 passed", "commit": "37c5295",
      "retries": 0, "repairs": 1, "handoffs": 0 }
  ],
  "singlePass": null,
  "tests": "make check -> 127 passed (было 115 на старте прогона); make pre-commit-run -> все хуки Passed; прогон по 38 настоящим скиллам распределение не сдвинул",
  "debt": { "placeholders": [], "assumptions": [], "emptyEnv": [] },
  "additions": [],
  "coverage": { "findings": 7, "missing": 2, "halfCovered": 2, "unparentedAdditions": 3, "actedOn": "две дыры и две полупокрытые закрыты правкой спецификации до запуска тасков: русский текст в самом AGENTS.md, нечитаемый SKILL.md, какой код у какой стороны отказа, состав русских README. Три «сверх брифа» оставлены: расширение правки пути на все файлы .autopilot (тот же дефект в тех же файлах), имя ветки, раздел Вне рамок" },
  "concerns": [
    { "from": "02", "axis": "craft", "where": "AGENTS.md:113", "status": "снято",
      "what": "строка сужала код 6 до папки скилла, а тем же кодом выходил нечитаемый файл описания",
      "condition": "закрылось починкой таска 01: отказ описаний ушёл в код 3, строка верна без правки — проверено прогоном" },
    { "from": "02", "axis": "craft", "where": "AGENTS.md:113", "status": "снято",
      "what": "хвост «every outcome still prints a report» был обещанием, а не описанием",
      "condition": "закрылось починкой таска 01: дата в заголовке даёт код 1 с отчётом и без трассировки — проверено прогоном" }
  ],
  "reviewers": { "manifestSpec": "rev-manifest-spec", "craft": "rev-craft" },
  "blind": { "ran": null, "skipped": "прогон целиком состоит из находок независимого ревью PR #49 — оно и есть слепая проверка: обе оси перепроверяли каждую правку запуском, а не чтением. Вместо G4 сделан прогон по 38 настоящим скиллам: распределение 12 чисто / 6 с потерями / 17 отказ / 3 без SKILL.md не сдвинулось" }
}
