window.STATE =
{
  "slug": "env-specs-gate",
  "dir": "2026-09-14-env-specs-gate--wip",
  "title": "Описания сред Claude Code и Antigravity + гейт FR-48",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-14-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "/Users/kksudo/.agents/skills/autopilot",
  "startedAt": "2026-09-14T00:07:56+04:00",
  "updatedAt": "2026-09-14T00:22:29+04:00",
  "finishedAt": null,
  "stages": [
    {
      "id": "preflight",
      "status": "done",
      "startedAt": "2026-09-14T00:07:56+04:00",
      "finishedAt": "2026-09-14T00:09:05+04:00"
    },
    {
      "id": "manifest",
      "status": "active",
      "startedAt": "2026-09-14T00:09:05+04:00"
    },
    {
      "id": "briefing",
      "status": "pending"
    },
    {
      "id": "spec",
      "status": "pending"
    },
    {
      "id": "plan",
      "status": "pending"
    },
    {
      "id": "build",
      "status": "pending"
    },
    {
      "id": "review",
      "status": "pending"
    },
    {
      "id": "final",
      "status": "pending"
    }
  ],
  "requirements": {
    "total": 35,
    "done": 0,
    "inTicket": 25,
    "inSpec": 0,
    "placeholder": 0,
    "deferred": 10,
    "dropped": 0
  },
  "tickets": [
    {"id": "01", "title": "Форма описания среды, нормализация и хеш", "requirements": ["R01", "R02", "R03", "R04", "R32i", "R34i"], "blockedBy": [], "wave": 1, "zone": ["src/agent_skill_adapter/envspec/"], "status": "pending", "retries": 0, "repairs": 0, "handoffs": 0},
    {"id": "02", "title": "Выбор описания по версии и проверка устаревания", "requirements": ["R05", "R08", "R17", "R22", "R29"], "blockedBy": ["01"], "wave": 2, "zone": ["src/agent_skill_adapter/envspec/loader.py"], "status": "pending", "retries": 0, "repairs": 0, "handoffs": 0},
    {"id": "03", "title": "Описание среды Claude Code", "requirements": ["R03", "R05", "R21", "R26", "R28", "R33i"], "blockedBy": ["01"], "wave": 2, "zone": ["specs/anthropic/"], "status": "pending", "retries": 0, "repairs": 0, "handoffs": 0},
    {"id": "04", "title": "Описание среды Google Antigravity", "requirements": ["R03", "R05", "R21", "R26", "R27", "R33i"], "blockedBy": ["01"], "wave": 2, "zone": ["specs/google/"], "status": "pending", "retries": 0, "repairs": 0, "handoffs": 0},
    {"id": "05", "title": "Перечень пробелов и критерий продолжения", "requirements": ["R24", "R25", "R31"], "blockedBy": ["02", "03", "04"], "wave": 3, "zone": ["src/agent_skill_adapter/envspec/gaps.py", "specs/gaps/"], "status": "pending", "retries": 0, "repairs": 0, "handoffs": 0},
    {"id": "06", "title": "Сверка с документацией поставщика", "requirements": ["R12", "R13", "R14", "R15", "R19"], "blockedBy": ["02"], "wave": 3, "zone": ["src/agent_skill_adapter/envspec/freshness.py"], "status": "pending", "retries": 0, "repairs": 0, "handoffs": 0}
  ],
  "singlePass": null,
  "tests": null,
  "debt": {
    "placeholders": [],
    "assumptions": [],
    "emptyEnv": []
  },
  "additions": [],
  "coverage": {"findings": 12, "missing": 5, "half": 6, "extra": 4, "acted": "5 дописано в спецификацию (в т.ч. новое требование R35 — структура папок среды), 6 уточнено до однозначности, 1 переформулировано: код возврата перечня пробелов объявлен свойством команды разработчика, а не исходом адаптера по FR-27; 3 «лишних» оставлены — они прикреплены к требованиям R26/R27/R28 манифеста"},
  "concerns": [],
  "reviewers": {
    "manifestSpec": null,
    "craft": null
  },
  "blind": null
}
