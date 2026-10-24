# ML Research Radar — Scientific Entity v0.4 Root-Cause Triage

**Версия:** предварительный аналитический обзор 30 из 76 случаев · 24 октября 2026

**Статус:** диагностические гипотезы, не новые ground-truth labels и не решение о качестве v0.4.

## Источники и контроль

- `review_items.jsonl`: 76 объектов из 58 разных полей; исходные тексты и spans проверены по SHA-256/координатам (76/76).
- `sampling_manifest.json`: страты и lineage совпадают с выбранной очередью; источник — исторический 9D audit.
- Выбранные 30 примеров — экспертно ориентированная диагностическая подвыборка из уже отобранной очереди, **не репрезентативная случайная выборка**.
- Все исходные строки имеют `review_status=pending`. Здесь предложены предварительные заметки в отдельном документе; исходные артефакты не изменены.
- Без чтения промежуточных GLiNER candidates нельзя локализовать причину пропуска на конкретной стадии (генерация кандидатов, фильтр, финализация).

## Подтверждённые результаты 9D (не переоценивались)

- Production H2 v0.3: 846 264 предсказаний на 61 075 статьях.
- 9D: 120 полей, 972 gold (904 certain + 68 uncertain).
- Primary typed-exact: Precision **40,88%**, Recall **36,95%**, F1 **38,81%**.
- По 9D диагностическому matching: 421 residual FN; 334 residual FP; 114 exact-span/wrong-type; 26 boundary-only; 9 both-boundary-and-type.
- Результаты относятся к сбалансированной выборке title/abstract, а не автоматически ко всей популяции корпуса.

## Предварительный просмотр 30 случаев

**Обозначения:** G — эталон (gold), P — production prediction, «—» — отсутствует в соответствующей диагностической категории. «Высокая/средняя» — уверенность в интерпретации примера, а не оценка вероятности ошибки.

### Полностью пустые title (6)

**#01** · `title` · G: `Multilingual Open Text Release 1` (dataset) · P: —
- **Паттерн:** Пропуск именованного dataset. **Уверенность:** высокая. В заголовке явно назван конкретный корпус Multilingual Open Text Release 1; финальных предсказаний нет.
- **Контекст:** Multilingual Open Text Release 1: Public Domain News in 44 Languages

**#02** · `title` · G: `Long Videos` (domain) · P: —
- **Паттерн:** Пропуск + вопрос к taxonomy. **Уверенность:** средняя. Long Videos обозначает характеристику видео/данных; считать ли это отдельным domain, нужно решать по guidelines.
- **Контекст:** Self-Supervised Animal Identification for Long Videos

**#03** · `title` · G: `Selective Engagement` (method) · P: —
- **Паттерн:** Пропуск метода + терминологическая неоднозначность. **Уверенность:** средняя. Selective Engagement звучит как название механизма коммуникации; контекст заголовка поддерживает method, но термин может быть общим.
- **Контекст:** T2MAC: Targeted and Trusted Multi-Agent Communication through Selective Engagement and Evidence-Driven Integration

**#04** · `title` · G: `Document-Level Event Extraction` (task) · P: —
- **Паттерн:** Пропуск явной task. **Уверенность:** высокая. Document-Level Event Extraction — явно сформулированная научная задача; предсказаний нет.
- **Контекст:** Document-Level Event Extraction via Human-Like Reading Process

**#05** · `title` · G: `optical camera communication` (domain) · P: —
- **Паттерн:** Пропуск domain. **Уверенность:** высокая. Optical camera communication обозначает предметную/прикладную область в заголовке; нет предсказаний.
- **Контекст:** Efficient demodulation scheme for multilevel modulation based optical camera communication

**#06** · `title` · G: `multilevel modulation` (method) · P: —
- **Паттерн:** Пропуск method. **Уверенность:** высокая. Multilevel modulation — конкретный метод/техника, не найден в том же заголовке.
- **Контекст:** Efficient demodulation scheme for multilevel modulation based optical camera communication


### Несопоставленные gold (6)

**#07** · `title` · G: `Homogeneous and Heterogeneous Remote Sensing Images` (domain) · P: —
- **Паттерн:** Пропуск domain, длинная именная группа. **Уверенность:** высокая. Полный тип данных/среда remote sensing images не выделен; нельзя утверждать, что виновата длина без candidate traces.
- **Контекст:** A Multiscale Graph Convolutional Network for Change Detection in Homogeneous and Heterogeneous Remote Sensing Images

**#08** · `title` · G: `Fine tuning` (method) · P: —
- **Паттерн:** Пропуск общего методического термина. **Уверенность:** средняя. Fine tuning обозначает технический метод, но это общая фраза, и policy извлечения может по-разному трактовать её.
- **Контекст:** Fine tuning U-Net for ultrasound image segmentation: which layers?

**#09** · `title` · G: `LSTM` (model) · P: —
- **Паттерн:** Пропуск обозначения модельной архитектуры. **Уверенность:** высокая. LSTM в заголовке обозначает архитектуру; в production-результате нет соответствующей пары.
- **Контекст:** Multivariate LSTM-Based Forecasting for Renewable Energy: Enhancing Climate Change Mitigation

**#10** · `title` · G: `Speech Enhancement` (task) · P: —
- **Паттерн:** Пропуск явной task. **Уверенность:** высокая. Speech Enhancement — стандартная формулировка задачи в заголовке.
- **Контекст:** Conditional Latent Diffusion-Based Speech Enhancement Via Dual Context Learning

**#11** · `abstract` · G: `GEBD benchmark dataset` (dataset) · P: —
- **Паттерн:** Пропуск явно названного dataset. **Уверенность:** высокая. GEBD benchmark dataset относится к конкретному benchmark, а не общему слову data.
- **Контекст:** …r temporal relationship for later boundary score estimation. Extensive experiments conducted on the GEBD benchmark dataset show the effectiveness of our system and its variations, in which we outperformed the state-of-the-art a…

**#14** · `abstract` · G: `query queuing time` (metric) · P: —
- **Паттерн:** Пропуск metric / уточнение конвенции. **Уверенность:** средняя. Query queuing time — измеряемый компонент latency; проверить единообразие разметки терминов времени.
- **Контекст:** …xecution order and timing of queries to enhance total end-to-end runtime as experienced by the user query queuing time plus system runtime. Unlike previous approaches, IconqSched features a novel fine-grained predictor, Ico…


### Несопоставленные predictions (6)

**#27** · `title` · G: — · P: `EEG` (dataset)
- **Паттерн:** Общий тип данных ошибочно принят за dataset. **Уверенность:** высокая. EEG в выражении EEG data — модальность, не имя датасета.
- **Контекст:** BENDR: using transformers and a contrastive self-supervised learning task to learn from massive amounts of EEG data

**#28** · `title` · G: — · P: `deep learning` (method)
- **Паттерн:** Общий термин method: вопрос к policy. **Уверенность:** средняя. Deep learning описывает широкий класс методов; отсутствие в gold может быть намеренным либо непоследовательной разметкой.
- **Контекст:** PoTrojan: powerful neural-level trojan designs in deep learning models

**#29** · `title` · G: — · P: `Efficiency` (metric)
- **Паттерн:** Общее оценочное слово ошибочно принято за metric. **Уверенность:** высокая. Efficiency в начале заголовка не называет конкретную метрику.
- **Контекст:** Efficiency and Effectiveness of LLM-Based Summarization of Evidence in Crowdsourced Fact-Checking

**#30** · `title` · G: — · P: `Neural Network` (model)
- **Паттерн:** Generic model label: вопрос к policy. **Уверенность:** средняя. Neural Network Architecture может обозначать широкий класс моделей; нужно явно решить, включаем ли такие типы в gold.
- **Контекст:** Neural Network Architecture for Database Augmentation Using Shared Features

**#31** · `title` · G: — · P: `Carbon Capture` (task)
- **Паттерн:** Task vs domain + неоднозначность. **Уверенность:** средняя. Carbon Capture — прикладная область / цель; классифицировать как task без более узкого операционального правила рискованно.
- **Контекст:** Advancing Carbon Capture using AI: Design of permeable membrane and estimation of parameters for Carbon Capture using linear regression and membrane-based equations

**#33** · `abstract` · G: — · P: `research` (domain)
- **Паттерн:** Слишком общий domain. **Уверенность:** высокая. Research само по себе не научная предметная область.
- **Контекст:** …t years, the classification of variable stars with machine learning has become a mainstream area of research. Recently, visualization of time series is attracting more attention in data science as a tool to visual…


### Точные границы, ошибочный тип (6)

**#47** · `title` · G: `Chest X-Ray Images` (domain) · P: `Chest X-Ray Images` (dataset)
- **Паттерн:** Путаница domain и dataset. **Уверенность:** высокая. Chest X-Ray Images — тип изображений; нет названия конкретного датасета.
- **Контекст:** A Two-Step Radiologist-Like Approach for Covid-19 Computer-Aided Diagnosis from Chest X-Ray Images

**#48** · `title` · G: `GraphRAG` (method) · P: `GraphRAG` (model)
- **Паттерн:** Путаница method и model, контекстозависимость. **Уверенность:** средняя. GraphRAG может обозначать метод или конкретную систему; в этом заголовке gold = method, неоднозначность стоит описать.
- **Контекст:** How to Mitigate Information Loss in Knowledge Graphs for GraphRAG: Leveraging Triple Context Restoration and Query-Driven Feedback

**#49** · `title` · G: `SIMPL` (model) · P: `SIMPL` (method)
- **Паттерн:** Именованная модель принята за method. **Уверенность:** средняя. SIMPL назван baseline для motion prediction; граница совпала, спор остаётся только о принятой таксономии.
- **Контекст:** SIMPL: A Simple and Efficient Multi-agent Motion Prediction Baseline for Autonomous Driving

**#50** · `title` · G: `Context-aware Neural Machine Translation` (task) · P: `Context-aware Neural Machine Translation` (method)
- **Паттерн:** Task классифицирована как method. **Уверенность:** высокая. Context-aware Neural Machine Translation здесь постановка задачи, для которой предложен selective attention.
- **Контекст:** Selective Attention for Context-aware Neural Machine Translation

**#51** · `abstract` · G: `Repeated MNIST` (dataset) · P: `Repeated MNIST` (task)
- **Паттерн:** Dataset классифицирован как task. **Уверенность:** высокая. Repeated MNIST явно benchmark/dataset в контексте сравнения методов.
- **Контекст:** …ents that PowerEvaluationBALD works on par with BatchEvaluationBALD, which outperforms BatchBALD on Repeated MNIST (MNISTx2), while massively reducing the computational requirements compared to BatchBALD or BatchEvaluat…

**#54** · `abstract` · G: `FID` (metric) · P: `FID` (task)
- **Паттерн:** Metric классифицирован как task. **Уверенность:** высокая. FID перечислен вместе с LPIPS/DISTS/KID как метрика качества.
- **Контекст:** …al performance, consistently outperforming traditional and deep-learning baselines on LPIPS, DISTS, FID, and KID. Source code will be publicly available at https://github.com/NJUVISION/YODA.


### Неверные границы, верный тип (4)

**#63** · `title` · G: `contrastive self-supervised learning` (method) · P: `self-supervised learning` (method)
- **Паттерн:** Усечение определения метода. **Уверенность:** высокая. Слово contrastive исключено из полного span метода; тип уже совпадает.
- **Контекст:** BENDR: using transformers and a contrastive self-supervised learning task to learn from massive amounts of EEG data

**#64** · `title` · G: `Video Implicit Neural Representations` (model) · P: `Neural Representations` (model)
- **Паттерн:** Усечение модификатора модели. **Уверенность:** высокая. Пропущено Video Implicit в названии типа представлений.
- **Контекст:** Bias for Action: Video Implicit Neural Representations with Bias Modulation

**#66** · `abstract` · G: `Virtual-Squat` (dataset) · P: `Virtual-Squat dataset` (dataset)
- **Паттерн:** Различие annotation span convention. **Уверенность:** средняя. Virtual-Squat vs Virtual-Squat dataset: предсказание содержит поясняющий head noun, который исключён из gold.
- **Контекст:** …cremental data. For evaluation, we created a novel exercise dataset with virtual avatars called the Virtual-Squat dataset. Overall, we claim that our novel architecture based on the GWR can use a learned exercise refer…

**#68** · `abstract` · G: `Adamic-Adar` (metric) · P: `Adamic-Adar measures` (metric)
- **Паттерн:** Различие annotation span convention. **Уверенность:** средняя. Adamic-Adar vs Adamic-Adar measures: в prediction включено описательное слово measures.
- **Контекст:** …dship prediction, temporal motifs yield better results than general heuristics, such as Jaccard and Adamic-Adar measures. We are also able to identify vendors with high accuracy and observe interesting patterns in ra…


### Неверные границы и тип (2)

**#73** · `abstract` · G: `diabetic foot ulcer` (domain) · P: `diabetic foot ulcer datasets` (dataset)
- **Паттерн:** Смешение предметной области и упоминания о datasets. **Уверенность:** средняя. Diabetic foot ulcer — область применения, а diabetic foot ulcer datasets — словосочетание о наборах данных без имени конкретного датасета.
- **Контекст:** This paper provides conceptual foundation and procedures used in the development of diabetic foot ulcer datasets over the past decade, with a timeline to demonstrate progress. We conduct a survey on data capt…

**#75** · `abstract` · G: `classification accuracy` (metric) · P: `classification` (task)
- **Паттерн:** Усечение metric и подмена task. **Уверенность:** высокая. Classification accuracy — метрика; classification само по себе может быть задачей, но это не то упоминание.
- **Контекст:** …he knowledge embedded in the pre-trained model and its strong comprehension ability, achieving high classification accuracy with an extremely small number of tunable parameters. Specifically, we introduce a lightweight trainable…

## Выводы из триажа (качественные, не частотная оценка)

1. **Пропуски целых сущностей.** В заголовках встречаются очевидные задачи, модели и именованные датасеты без соответствующих production predictions (например, `Document-Level Event Extraction`, `LSTM`, `Multilingual Open Text Release 1`). Это end-to-end symptom; стадия происхождения пока неизвестна.
2. **Ошибка generic-vs-named.** `EEG` размечен предсказанием как dataset, `Efficiency` как metric, `research` как domain. Нужна более чёткая практическая трактовка общих терминов и специфических названий.
3. **Confusion taxonomy.** `FID → task`, `Repeated MNIST → task`, `Chest X-Ray Images → dataset`, `Context-aware Neural Machine Translation → method` демонстрируют разные типы неверной классификации. Одного правила method→model недостаточно.
4. **Границы и согласованность эталона.** `contrastive self-supervised learning` усечён до `self-supervised learning`; `Virtual-Squat dataset` и `Adamic-Adar measures` отличаются от gold на описательный компонент. Некоторые пограничные случаи требуют явной span-convention, а не новой модели.
5. **Нужно различать ошибки модели и неоднозначность gold.** `Long Videos`, `Neural Network`, `deep learning`, `GraphRAG`, `Carbon Capture` зависят от строгой таксономии. Не переписываем historical gold; фиксируем конфликт как проблему инструкций/конвенций.

## Ограничения

- Эти 30 случаев выбраны для качественного анализа. Доли категорий внутри 30 нельзя переносить на 846 264 production mentions.
- Промежуточных результатов GLiNER/фильтрации здесь нет; гипотезы о конкретных стадиях следует проверять только в будущих targeted diagnostics.
- Текущие 120 полей и эта triage-очередь уже раскрыты; их нельзя использовать как новый независимый heldout для отбора модели v0.4.

## Решение о завершении текущего цикла

- **Сохранить** trusted H2 v0.3 и immutable 9B/9C/9D evidence без изменений.
- **Сохранить** исходную очередь 76 `pending`; этот обзор — отдельные заметки, не скрытая смена статусов.
- **Отложить** v0.4 experiments до возвращения к NER: приоритеты — missing detection, taxonomy/generic-vs-named, boundary policy.
- **Не делать** full corpus inference, threshold tuning или auto-promotion в текущем цикле.
- **Перейти** к следующему направлению ML Research Radar после компактного NER state/closure update.

## Следующий шаг при возврате к v0.4

1. Уточнить taxonomy и span convention на **новой development-разметке** с явным review ambiguities.
2. Для coverage misses отдельно собрать evidence от стадий candidate generation → filters → semantic typing → finalization.
3. Сравнить 1–2 ограниченных кандидата на новом dev, зафиксировать scoring/acceptance заранее; использовать новый независимый heldout перед production promotion.
