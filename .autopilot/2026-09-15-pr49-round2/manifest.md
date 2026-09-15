# Манифест требований

Источник: `2026-09-15-brief.md` — второй круг ревью PR #49.
Строку из этого списка может снять **только пользователь**.

| ID | Из брифа (дословно) | Статус | Основание | Где |
|----|---------------------|--------|-----------|-----|
| R01 | «`2026-09-14:` and `"2026-09-14":` … cause one value to overwrite the other before `hooks.json` is written» | done | — | коммит 87926ad |
| R02 | «Normalize mapping keys into a temporary mapping and refuse duplicate normalized keys. Add a regression test for this input.» | done | — | коммит 87926ad |
| R03 | «It does not detect two planned parts that expand to the same staged path… The later `copy2` overwrites the earlier file, while `written` reports both as successful» | done | — | коммит 87926ad |
| R04 | «Validate that planned staged paths are unique and do not overlap before the write loop. Return `COLLISION` when they do.» | done | — | коммит 87926ad |
| R05 | «A concurrent writer can replace a checked path component with a symlink, causing `mkdir()` or subsequent writes to escape `out`… Reject symlinks during every destination-path operation.» | done | — | коммит 87926ad |
| R06 | «`_assemble()` catches only `OSError`, and `convert()` also does not catch `shutil.Error`» | done | проверено запуском до начала: `shutil.Error` — подкласс `OSError`, случай уже даёт код 7 с отчётом | коммит 87926ad |
| R07i | *(подразумевается)* потерянное значение не пропадает молча — это то же обещание, ради которого чинился первый круг | done | — | коммит 87926ad |
| R08i | *(подразумевается)* правки идут в ту же ветку и тот же PR #49 | done | — | коммит 87926ad |
| R09i | *(подразумевается)* на каждый подтверждённый дефект есть тест, красный без правки | done | — | коммит 87926ad |
