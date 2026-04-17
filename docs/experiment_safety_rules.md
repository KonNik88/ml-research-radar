# ML Research Radar — Experiment Safety Rules

## Статус документа

Версия: `v1`  
Статус: `working safety policy`  
Язык: `ru`

---

## 1. Назначение

Этот документ фиксирует правила безопасной работы с экспериментами, кандидатными результатами и промежуточными артефактами в ML Research Radar.

Главная цель:

- не повредить текущий рабочий canonical corpus;
- не потерять восстановимый full state;
- не испортить retrieval / DB serving случайным экспериментом;
- отделить production-like latest от всех risky outputs.

---

## 2. Базовый принцип

**Любой рискованный, неполностью проверенный или экспериментальный результат  
должен жить отдельно от latest.**

Формула:

```text
experiment first
→ candidate output
→ sanity-check
→ explicit promotion
```

Никогда:

```text
experiment
→ overwrite latest
```

---

## 3. Что считается экспериментом

Экспериментом считается любой запуск, который:

- меняет reconcile inputs;
- использует selective snapshots напрямую;
- меняет merge policy;
- меняет source priorities;
- меняет ranking behaviour;
- меняет source filtering / corpus preset;
- использует новый или частично проверенный ingest path;
- выполняется без заранее зафиксированного contract path;
- предназначен для диагностики, а не для прямого promotion.

---

## 4. Классы артефактов

## 4.1. Stable latest artifacts
Это артефакты, на которые может опираться система как на текущее рабочее состояние.

Примеры:
- canonical latest
- retrieval manifest latest
- latest validation reports
- latest source/postpass audit reports
- latest baseline report

## 4.2. Candidate artifacts
Это результаты, которые ещё не прошли promotion.

Примеры:
- merged full snapshots
- reconciled candidate corpus
- recovered canonical outputs
- merged_incremental outputs
- timestamped refresh reports

## 4.3. Experimental artifacts
Это ad-hoc результаты, которые могут быть полезны для диагностики, но не входят в стабильный operational path.

Примеры:
- experimental reconcile outputs
- one-off scripts
- manual debug dumps
- alternative ranking outputs
- adhoc comparison files

---

## 5. Главное правило именования

### 5.1. Latest reserved
Суффикс / имя `latest` должен использоваться только для:
- текущего принятого состояния;
- артефакта, уже прошедшего sanity-check и promotion.

### 5.2. Для экспериментов использовать только timestamped outputs
Примеры безопасных имён:
- `documents.20260412T162220Z.jsonl`
- `canonical_documents.merged_incremental_20260412.jsonl`
- `known_issues_snapshot_20260414T162622Z.json`
- `retrieval_checks_20260414T162520Z.json`

### 5.3. Для candidate-стадии использовать явные маркеры
Желательные слова в имени:
- `candidate`
- `merged`
- `recovered`
- `experimental`
- `debug`

---

## 6. Правила для canonical corpus

### Нельзя
- писать экспериментальный reconcile output сразу в `canonical_documents.jsonl`;
- считать candidate output новым truth layer без проверки;
- продвигать latest, если multisource coverage аномально схлопнулась;
- использовать implicit latest input, если известно, что latest не гарантирует full merged state.

### Нужно
- сохранять candidate в отдельный файл;
- делать backup текущего latest перед promotion;
- проверять counts, multisource state, DOI coverage и targeted samples перед заменой latest.

---

## 7. Правила для alignment snapshots

### Нельзя
- заменять full alignment snapshot маленьким selective snapshot;
- считать latest selective snapshot новым полным состоянием слоя;
- запускать reconcile по latest alignment snapshots, если latest теперь указывает на selective batch.

### Нужно
- всегда отделять full snapshot от selective snapshot;
- после selective enrichment делать merge в новый merged full snapshot;
- только merged full snapshot считать допустимым input для downstream reconcile.

---

## 8. Правила для retrieval

### Нельзя
- перестраивать retrieval на непроверенном canonical candidate;
- обновлять retrieval latest до promotion canonical;
- смешивать retrieval artifacts, собранные по разным canonical states.

### Нужно
- rebuild retrieval только после promotion canonical latest;
- сохранять новый build id;
- проверять `canonical_doc_count == retrieval_doc_count`.

---

## 9. Правила для Postgres export

### Нельзя
- экспортировать экспериментальный canonical candidate в production-like DB state без осознанного решения;
- считать DB более авторитетным, чем canonical latest.

### Нужно
- экспортировать только после promotion canonical;
- проверять counts после export;
- сохранять export run как часть operational trace.

---

## 10. Правила для validation и audit

### Нужно
- рассматривать validation как часть safety layer, а не как опциональную косметику;
- после значимого refresh обновлять:
  - retrieval checks
  - post-pass audit
- known issues snapshot обновлять желательно, особенно после milestone-level change

### Нельзя
- продвигать новый state, если уже на basic validation видно явное ухудшение structural integrity.

---

## 11. Правила доверия к скриптам

### 11.1. Trusted scripts
Это скрипты, которые уже многократно дали корректные результаты и входят в рабочий path.

### 11.2. Conditionally trusted scripts
Это скрипты, полезные для targeted diagnostics, но требующие дополнительной интерпретации.

### 11.3. Untrusted scripts
Если скрипт:
- не нормализует DOI/IDs,
- ищет не по полям, а по сырым строкам,
- даёт ложные false negatives,
- уже был уличён в misleading behaviour,

то он не должен использоваться как gate для promotion.

### Правило
Недоверенный script:
- можно оставить для отладки,
- но нельзя включать в blocking refresh path.

---

## 12. Sanity-check minimum before promotion

Перед promotion minimum sanity-check должен включать:

1. doc count выглядит правдоподобно;
2. multisource docs не схлопнулись неожиданно;
3. DOI-covered incremental candidates представлены корректно;
4. candidate structurally согласуется с ожиданием по source coverage;
5. targeted manual spot-check не выявил грубых inconsistencies;
6. нет явного конфликта между canonical / retrieval / export logic.

---

## 13. Rollback policy

### 13.1. Перед risky promotion
Всегда должен существовать backup предыдущего latest.

### 13.2. Если promotion оказался ошибочным
Нужно уметь быстро восстановить:
- previous canonical latest
- previous retrieval latest
- при необходимости previous DB state через повторный export из корректного canonical latest

### 13.3. Принцип rollback
Rollback должен опираться на:
- предыдущий trusted canonical
- предыдущий trusted retrieval build
- сохранённые timestamped artifacts

---

## 14. Safe execution modes

## 14.1. Safe mode
Безопасный режим:

- timestamped outputs
- explicit inputs
- no overwrite latest
- candidate-only writes

## 14.2. Controlled promotion mode
Режим controlled promotion:

- есть candidate
- есть sanity-check
- есть backup
- есть явное решение обновить latest

## 14.3. Unsafe mode
Небезопасный режим:

- implicit latest-based reconcile при неоднозначном latest state
- overwrite latest during experiment
- mixed source states
- rebuild retrieval before canonical promotion

Такой режим должен считаться запрещённым.

---

## 15. Правила для orchestration в будущем

Когда refresh path будет автоматизироваться, orchestration обязана:

1. различать full и selective snapshots;
2. различать candidate и latest outputs;
3. использовать explicit merged inputs для reconcile;
4. не промоутить latest автоматически без success gates;
5. сохранять baseline и execution trace;
6. уметь завершиться безопасно без partial destructive overwrite.

---

## 16. Чего не делать “ради удобства”

Нельзя упрощать пайплайн так, чтобы:

- selective snapshot стал full truth по умолчанию;
- latest начал означать “последний файл”, а не “последний доверенный файл”;
- promotion происходил автоматически только потому, что шаг завершился с `returncode=0`;
- success команды подменял собой success данных.

---

## 17. Safety summary

Проект должен жить по простой формуле:

```text
latest = trusted state
candidate = untrusted until checked
timestamped outputs = default for experiments
promotion = explicit action
rollback = always possible
```

---

## 18. Практический итог для текущего этапа

На текущем этапе проекта безопасная стратегия такая:

1. сначала зафиксировать refresh contract;
2. потом отделить safety rules;
3. затем автоматизировать только уже доказанный path;
4. не расширять feature surface, пока latest/candidate semantics не формализованы.

Это обязательнее, чем новые product layers.
