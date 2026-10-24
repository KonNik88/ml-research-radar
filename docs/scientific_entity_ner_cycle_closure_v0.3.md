# ML Research Radar — Scientific Entity NER: Research Cycle Closure v0.3

**Решение от:** 2026-10-24  
**Тип документа:** checkpoint / handoff, только документация  
**Статус:** текущий исследовательский цикл NER v0.3 завершён; дальнейшие улучшения перенесены в backlog v0.4  
**Production:** trusted H2 v0.3 сохраняется без изменений  
**Публикация / новая promotion:** не разрешены этим документом

> **Scope.** Закрывается активный *исследовательский цикл* Scientific Entity NER, а не функциональность NER в Radar. Ни canonical corpus, ни frozen evaluation, ни production latest не меняются. Документ не является новым acceptance gate, артефактом модели, миграцией БД или разрешением на публикацию данных.

## 1. Decision / executive summary

1. Сохранить текущий `scientific_entity_semantic_typer_h2` **v0.3** как trusted production latest и воспроизводимую историческую базу.
2. Признать завершёнными full-corpus materialization, controlled promotion/closure, независимый full-field audit 9A–9D и read-only диагностику 9E / v0.4-A в пределах выполненной работы.
3. Зафиксировать независимую **typed-exact F1 = 0.3881464264962231** как измеренное качество end-to-end NER на сбалансированной выборке 60 title / 60 abstract; **не** выдавать число за population-weighted оценку качества всех 61 075 статей.
4. Не менять frozen reference или scoring policy после unblind; не подбирать thresholds и не проводить model selection по 120 раскрытым полям.
5. Оставить 76-case диагностическую очередь в качестве исторического read-only материала; отдельно выполнен предварительный качественный разбор **30/76** случаев. Исходные `review_items.jsonl` не превращены в новый gold и остаются в статусе `pending`.
6. Отложить полноценный v0.4: новые dev/heldout-аннотации, candidate-stage tracing, отбор моделей, дополнительные GLiNER/H2 experiments и full-corpus inference.
7. Переключить активную разработку на следующий вертикальный срез Radar, предварительно сверив актуальное состояние retrieval/API/Postgres/Qdrant/Discovery по текущему репозиторию и не повторяя реализованное ранее.

**Важно:** успешная инженерная приёмка H2 и его selective typing policy не эквивалентны высокому end-to-end качеству полного NER. Оба утверждения корректны одновременно.

## 2. База данных, идентичности и инварианты

- Paper source of truth: `data/analytics/reconciled/canonical_documents.jsonl`.
- Принятая canonical база: **61 075** papers; canonical SHA-256: `3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff`.
- `canonical_id` остаётся идентичностью статьи; `final_mention_id` — идентичностью содержательного упоминания, **не уникальным идентификатором физической строки**. Повтор одинакового предсказания не должен silently deduplicate: лишняя несопоставленная копия учитывается как FP согласно 9C.
- Scientific Entity — производный evidence/materialization layer, не paper truth и не основание изменять canonical reconciliation.
- Шесть классов: `task`, `method`, `model`, `dataset`, `metric`, `domain`.
- Никакой downstream consumer не должен трактовать автоматически предсказанные типы/границы как проверенную вручную истину.

## 3. Принятая production-база H2 v0.3

| Параметр | Фиксированное значение |
|---|---|
| Candidate build ID | `scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z` |
| Candidate ID | `scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method` |
| Canonical papers | `61075` |
| Final mention rows | **846264** |
| H2 selective method→model overrides | **33469** |
| Final mentions SHA-256 | `518f3984d3dcd2aa5e2a84c96eec2fadce8b6dc6b49eef0d7a908533145394c1` |
| Latest pointer | `data/entities/scientific_entity_production/v0.3/latest.json` |
| Pointer state | `trusted_latest` |
| Publication authorized | `false` |

Immutable candidate file:

```text
data/entities/scientific_entity_semantic_typer_h2_full_corpus_candidate/v0.3/
  scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z/
    final_mentions.jsonl
```

Контролируемые production promotion, post-promotion checks, rollback readiness и H2 lifecycle closure ранее прошли свои отдельные проверки. **Этот closure не переключает указатель, не производит повторный inference и не создаёт новый production candidate.**

## 4. История экспериментального цикла — кратко

| Линия работы | Статус / роль |
|---|---|
| Literal evidence baseline, bounded GLiNER adapter, calibration | Реализованы как исследовательские baseline и контролируемые кандидаты |
| Semantic prompt v0.2a, threshold calibration v0.2b, raw-floor v0.2c | Контролируемые development experiments; v0.2c впоследствии **отклонён** независимым acceptance decision, не задним числом переписан |
| v0.3 typing diagnostics | Анализ ошибок типов; выделенные случаи стали основанием для ограниченной H1/H2 работы |
| H1 | Не принят из-за регрессий по критериям соответствующей линии оценки |
| H2 selective semantic typer | Принят после своих независимых gate / audit / authorization и материализован на всём canonical corpus |
| 9A–9D Full NER Coverage Audit | Независимая оценка **полного** end-to-end extractor, а не только селективной коррекции H2 |
| 9E, v0.4-A root-cause review | Read-only анализ исторических ошибок; **не** кандидат v0.4 и **не** новый acceptance |

Ранние F1 получены на других тестовых наборах и с другой целью. Не интерпретировать их прямое сравнение с 9D F1 как доказательство роста или регрессии одной и той же измеряемой популяции.

## 5. Full NER Coverage Audit 9A–9D: immutable evidence

### Lineage / freeze

- Audit ID: `scientific-entity-full-ner-coverage-audit-v0.1-3cc6e3c779fee351`.
- Frozen reference ID: `scientific-entity-full-ner-coverage-reference-v0.1-3cc6e3c779fee351`.
- Reference annotations SHA-256: `95e231b4187de26fa57d9c71b3ec74c4d5303ce3c22c5a96560059c948235c75`.
- Scoring policy ID: `scientific-entity-full-ner-coverage-scoring-policy-v0.1-3cc6e3c779fee351`.
- Evaluation ID: `scientific-entity-full-ner-coverage-unblind-evaluation-v0.1-3cc6e3c779fee351`.
- Evaluation manifest SHA-256: `88b0f1bb0acf3c8faa2fcac93cef966504612dd0dfb43960b77a0bfd14748bfb`.
- 120 целых полей: 60 title + 60 abstract; 972 mentions, из них 904 certain и 68 uncertain.
- Из 851 выбранного production prediction 34 исключены из primary scoring по предзарегистрированному `uncertain-only` правилу; 817 предсказаний участвовали в primary panel.
- Unblind был сделан после freeze scoring policy; 9D завершён с **22/22** строгими проверками, без нового model inference и без мутации production / policy / reference.

### Primary metrics (type-aware exact)

| P | R | F1 | TP | FP | FN |
|---:|---:|---:|---:|---:|---:|
| 0.4088127295 | 0.3694690265 | **0.3881464265** | 334 | 483 | 570 |

### Secondary metrics

| Evaluation panel | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|
| Span-only exact | 0.5206275421 | 448 | 369 | 456 |
| Typed relaxed, IoU ≥ 0.5 | 0.4218477629 | 363 | 454 | 541 |
| Span-only relaxed, IoU ≥ 0.5 | 0.5613015689 | 483 | 334 | 421 |

### Primary F1 by type

| Type | Gold support | Scored predictions | Exact F1 |
|---|---:|---:|---:|
| `model` | 213 | 249 | 0.5411 |
| `method` | 292 | 252 | 0.4007 |
| `metric` | 75 | 68 | 0.3357 |
| `task` | 188 | 143 | 0.3263 |
| `dataset` | 28 | 72 | 0.2200 |
| `domain` | 108 | 33 | 0.1560 |

### Diagnostic error partition

- 114 exact-span / wrong-type pairs.
- 26 boundary-only / same-type pairs.
- 9 boundary-and-type pairs.
- 421 residual unmatched reference mentions.
- 334 residual unmatched predictions.

Эти категории объясняют 570 FN и 483 FP в primary panel. **421 residual FN нельзя автоматически назвать 421 полностью отсутствующими concepts:** в остатке возможны слабые overlap или ограничения диагностического matching. Точные root causes требуют просмотра кандидатных стадий.

Дополнительные признаки: `domain` — низкий recall, `dataset` — большая доля лишних/неверных предсказаний; `model` относительно сильнее остальных классов. На balanced sample F1 title и abstract близки (0.3929 и 0.3874), но title имеет меньший recall. 13/60 заголовков не получили ни одного prediction при наличии хотя бы одного certain reference.

**Ограничение интерпретации:** 60/60 title/abstract — спроектированная сбалансированная выборка, не естественное распределение всех упоминаний/полей в corpus; метрики не являются population-weighted оценкой. Числовое gate-решение «quality pass/fail» данным audit не принималось. `publication_authorized=false`.

## 6. Read-only 9E / v0.4-A review: что выполнено и что нет

- Work queue ID: `scientific-entity-v04-root-cause-review-v0.1-3cc6e3c779fee351`.
- Queue: **76** записей из **58** разных полей, 34 title / 42 abstract; исходные SHA/text offsets проверены при подготовке диагностики.
- Страты: `zero_prediction_title=6`, `residual_fn=20`, `residual_fp=20`, `type_only_exact_span=16`, `boundary_only_same_type=8`, `boundary_and_type=6`.
- Выполнен отдельный **предварительный качественный разбор 30/76** с письменными замечаниями. Это purposive sample для гипотез, не частотная оценка на корпус.
- **46/76** записей не разбирались содержательно; status исходной очереди `pending` не менялся. Не выдавать отдельные заметки за completed human labels в самой очереди.
- Production predictions, reference, thresholds, trusted latest не были изменены.

Зафиксированные наблюдения / примеры:

1. End-to-end omissions: `Document-Level Event Extraction`, `LSTM`, именованные corpora/datasets могут отсутствовать в финальных predictions; без промежуточных candidate traces неизвестно, на какой стадии потерялось упоминание.
2. Generic / scope precision: `EEG` как `dataset`, `Efficiency` как `metric`, `research` как `domain`; не все такие ошибки эквивалентны ложному обнаружению из-за возможных неоднозначностей annotation guide.
3. Taxonomy: `FID` ошибочно как `task` вместо `metric`; `Repeated MNIST` как `task` вместо `dataset`; `Chest X-Ray Images` как `dataset` вместо `domain`; типизация не ограничивается H2 `method→model`.
4. Boundaries: `contrastive self-supervised learning` vs `self-supervised learning`; некоторые другие отличия (`Virtual-Squat` vs `Virtual-Squat dataset`) отражают span convention и нуждаются в однозначном future guide.
5. Ambiguous gold / convention-sensitive cases: `Long Videos`, `GraphRAG`, `Carbon Capture` — не пересматривать исторический frozen gold задним числом.

Источники для handoff (проверять актуальные файлы в репозитории):

- `docs/scientific_entity_full_ner_coverage_results_review_v0.1.md` — 9E quantitative review.
- `docs/scientific_entity_v04_root_cause_diagnostics_v0.1.md` — методика составления очереди.
- Локальные `data/entities/scientific_entity_v04_root_cause_review_work/v0.1/.../review_items.jsonl` и `sampling_manifest.json` — read-only work evidence; **не коммитить в Git** без отдельной policy/причины.
- `docs/scientific_entity_v04_root_cause_triage_30_v0.1.md` — отдельные качественные заметки по 30 рассмотренным случаям; не являются новым gold или пересмотром frozen reference.

## 7. Решение о v0.4 и строгие ограничения при возвращении

**Сейчас не выполнять:**

- сбор новой development-разметки для подгонки candidate v0.4;
- переобучение, prompt/policy/threshold tuning, H2 retuning;
- реинференс на всех 61 075 статьях;
- изменение H2 trusted latest или перезапись 9B/9C/9D;
- автоматическую публикацию датасета/метрик как quality-approved release.

**Отложенный backlog (при отдельном решении вернуться к NER):**

1. Развести причинные стадии `candidate generation → filtering → semantic typing → finalization`: для новых dev-примеров собрать stage-by-stage traces и замерить, где исчезают entities.
2. Уточнить taxonomy и span conventions для именованных сущностей, generic phrases и доменных типов на **новой независимой development-разметке**; спорные случаи явно adjudicate.
3. Проверить не более 1–2 ограниченных гипотез: (a) recall в `task/domain` и именованных моделях/датасетах; (b) generic false positives и taxonomy confusions.
4. Для model selection использовать **fresh development** вне 9D. Для независимой проверки после настройки подготовить ещё один **disjoint fresh heldout** и заранее зарегистрировать scoring/acceptance criteria.
5. Full-corpus candidate, heavy inference и controlled promotion обсуждать **только после** положительного independent acceptance и явного разрешения затратного запуска; отдельно предупредить о возможном многочасовом выполнении.

Исторические 120 9D fields и раскрытые 76 review cases разрешены только для постановки и иллюстрации гипотез, регрессионной диагностики и документации; **запрещено** представлять их новым независимым heldout v0.4.

## 8. Что допускается при интеграции NER в Radar

- Использовать H2 v0.3 как **вспомогательные, вероятностные structured signals** для поиска, фильтров, аналитики и объяснимых evidence views — только с атрибуцией derivation lineage и понятными оговорками о точности.
- Не заменять NER-предсказаниями paper truth и не подавлять поиск по статье, если entity отсутствует: низкий recall `domain/task` делает hard-filter-only сценарии рискованными.
- До показа пользователям выяснить, какие конкретные NER outputs уже доступны через Postgres/API/UI и какие существуют пока только как immutable JSONL. Текущим документом полнота такой интеграции **не подтверждается**.
- Публичную выгрузку entity data/labels не разрешать автоматически: учитывать ограничения источников и политику dataset redistribution; `publication_authorized=false`.

## 9. Передача управления следующему слою Radar

**Рекомендуемый первый шаг: read-only inventory current serving/retrieval state.** Проверить актуальные `docs/project_state_current_v0.2.md`, `docs/roadmap.md`, routes `/search`, Postgres backend, Qdrant/vector serving, текущий retrieval generation, golden evaluation и Discovery UI. В раннем roadmap и September checkpoint часть состояний была отмечена как planned/experimental, поэтому нельзя начинать новый функциональный срез, не проверив текущий репозиторий.

**Предварительная линия приоритета из master plan:** search/retrieval quality и DB/vector serving parity → зрелость backend и API → observability/orchestration → более сложные RAG/graph/UI функции. Это предложение по последовательности; точную следующую задачу выбирать после проверки фактического Git `main` и живого roadmap.

### Exit criteria / closure DoD

- [x] H2 v0.3 trusted latest зафиксирован и остаётся неизменным.
- [x] 9B reference / 9C preregistered policy / 9D evaluation строго проверены.
- [x] 9E quantitative review и предварительные 30-case root-cause notes выполнены.
- [x] Отложенные риски и v0.4 backlog описаны без выдачи гипотез за доказанные причины.
- [x] Решение прекратить новый NER inference/tuning в текущем цикле принято.
- [ ] Настоящий closure-документ зафиксирован коммитом в текущем Git `main` через обычную ветку/PR.
- [ ] Живые `docs/project_state_current_v0.2.md` и `docs/roadmap.md` согласованно обновлены без потери последующих записей.
- [ ] Определён следующий вертикальный срез после read-only state inventory.

## 10. Ссылки на воспроизводимую проверку (без перезаписи)

Read-only validators, доступные в репозитории при наличии соответствующих модулей:

```bash
python -m scripts.validation.check_scientific_entity_full_ner_coverage_reference --strict
python -m scripts.validation.check_scientific_entity_full_ner_coverage_scoring_policy --strict
python -m scripts.validation.check_scientific_entity_full_ner_coverage_unblind_evaluation --strict
```

Не запускать `... --execute`, `full-corpus inference`, `promotion`, `threshold tuning` для выполнения *этого* документа. Успешные результаты предыдущих строгих проверок сохраняются как исторические evidence; новые проверки не обязательны при отсутствии модификаций артефактов.

---

**Final state:** `ner_active_research_cycle = completed / deferred`, `trusted_production = H2 v0.3`, `current_quality_evidence = 9D balanced full-field audit`, `next_research = deferred v0.4`, `other_radar_layers = resumed after live-state inventory`.
