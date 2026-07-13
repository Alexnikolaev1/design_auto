# LayoutGenius

Веб-сервис: загружаете `.docx` → получаете 5 вариантов профессиональной
вёрстки (A4, книжная ориентация) для Adobe InDesign CS3 в формате INX,
с превью и ZIP-архивом (`layout.inx` + `Links/` + `Fonts/` +
`preflight_report.txt` + `README.txt`).

## Быстрый старт локально

```bash
docker compose up --build
# открыть http://localhost:8000
```

Для `.doc` без Docker нужен **LibreOffice** (`soffice`) или Microsoft Word (Windows COM).

Без Docker:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# системные пакеты (Debian/Ubuntu): fonts-liberation fonts-dejavu-core
uvicorn app.main:app --reload
```

## Деплой на Railway

1. Создайте новый проект на [railway.app](https://railway.app) → **Deploy from GitHub repo**,
   подключив репозиторий с этим кодом (в корне должен лежать `Dockerfile`, Railway
   определит его автоматически как способ сборки).
2. В Settings проекта Railway сам пробрасывает переменную `PORT` — `Dockerfile`
   уже её использует (`uvicorn ... --port ${PORT:-8000}`), ничего дополнительно
   настраивать не нужно.
3. Variables (не обязательные, но рекомендуемые):
   - `UNSPLASH_ACCESS_KEY` — ключ Unsplash API для автодобавления стоковых фото.
   - `PEXELS_API_KEY` — альтернативный/дополнительный источник стоковых фото.
   - `SECRET_KEY` — произвольная строка (сейчас не используется для сессий,
     зарезервировано на будущее).
   - `LG_MAX_UPLOAD_MB` — лимит размера загружаемого DOCX (по умолчанию 20).
   - `LG_MAX_PREVIEW_PAGES` — число PNG-превью на вариант (по умолчанию 8).
4. Deploy. Railway соберёт образ по `Dockerfile` и опубликует сервис на
   `https://<project>.up.railway.app`.

Второй (worker) сервис в текущей архитектуре не нужен — обработка идёт в
фоне внутри самого веб-процесса через `FastAPI BackgroundTasks` (подробности
и как перейти на Redis+RQ при масштабировании — см. `app/tasks/worker.py`).

## Архитектура

```
DOC/DOCX ─▶ parser/doc_converter.py (.doc→.docx) ─▶ docx_parser.py
                                        │
                        nlp/image_matcher.py │ привязка картинок + mapping.json
                        nlp/keywords.py    │ YAKE + стоковые фото
                        analysis/reference_pdf.py │ PDF-референсы
                                        ▼
                  layout/templates.py + ad_units.py (рекламные модули)
                                        │
                     layout/engine.py: пагинация, реклама, баннеры
                                        │
                     ┌──────────────────┼───────────────────┐
                     ▼                                       ▼
        preview/renderer.py (Pillow)              inx/generator.py (lxml)
        → PNG превью (до 8 стр.)                → layout.inx по страницам
                     │                              (Story на колонку)
                     └──────────────┬────────────────────────┘
                                    ▼
                    tasks/worker.py: ZIP (INX+Links+Fonts+mapping.json)
                                    ▼
                              main.py: REST API + static/
```

Точки входа REST API:
- `POST /api/jobs` — загрузка DOCX + профиль типографики → `job_id`.
- `GET /api/jobs/{job_id}` — статус (`queued/parsing/analyzing/laying_out/done/error`)
  и, при `done`, список из 5 результатов с превью и ссылками на скачивание.
- `GET /api/jobs/{job_id}/preview/{template_id}/{filename}` — PNG превью страницы.
- `GET /api/jobs/{job_id}/download/{template_id}` — ZIP с готовым макетом.

## Что реализовано по ТЗ как есть

- Приём **.doc и .docx**, drag-and-drop, извлечение текста с иерархией стилей.
- **Привязка иллюстраций** к разделам (7 стратегий + `mapping.json` в ZIP и API).
- **Рекламные модули** произвольного размера (мм, см²) с пометкой «Реклама».
- **PDF-референсы** — анализ полей, колонок, рекомендация шаблона.
- 5–6 шаблонов (в т.ч. «Рекламный буклет» при баннерах), PNG-превью до 8 страниц.
- INX: текст **постранично по колонкам** (совпадает с превью), изображения как Linked.
- Лимит размера загрузки, отсутствие исполнения макросов (python-docx работает
  только с XML-частями .docx), удаление временных файлов не требуется — всё
  живёт в `/tmp/layoutgenius_jobs/<job_id>` и может быть вычищено по cron/TTL
  на уровне инфраструктуры.

## Осознанные упрощения относительно исходного ТЗ (важно прочитать)

Я сознательно не стал изображать несуществующую полную реализацию там, где
это было бы нечестно. Вот три места, где сделаны реальные компромиссы:

1. **NLP**: вместо `spaCy(ru_core_news_sm) + YAKE` используется только YAKE.
   Русская модель spaCy весит десятки-сотни МБ и качается из внешних
   источников на этапе сборки образа — в среде, где собирался этот проект,
   нет сетевого доступа к этим источникам, и обязательная загрузка модели
   в `Dockerfile` была бы ненадёжной точкой отказа при деплое на Railway.
   YAKE — чистый Python без внешних моделей и на практике извлекает
   разумные ключевые слова для ru/en текста.
2. **Рендеринг превью**: вместо `Cairo + PangoCairo + uharfbuzz` используется
   Pillow. `pycairo`/`pygobject`-стек тянет системные GTK-библиотеки и
   регулярно ломается на slim-образах; Pillow даёт менее точный кернинг и не
   поддерживает сложные OpenType-фичи, но собирается предсказуемо в любом
   контейнере и даёт репрезентативное превью макета.
3. **Очередь задач**: вместо Redis+RQ — `FastAPI BackgroundTasks` + JSON-файл
   статуса на диске. Для одного веб-сервиса на Railway это проще и без
   лишней точки отказа. `process_job()` в `app/tasks/worker.py` написана так,
   что её можно вызвать и из RQ-таска без изменений, если понадобится
   горизонтальное масштабирование.
4. **Реальные шрифты PT Serif/PT Sans/Montserrat не включены в репозиторий**
   — см. `fonts/README.txt`: нет сетевого доступа к их источникам в этой
   среде сборки. Система работает с fallback на Liberation/DejaVu и явно
   помечает это в `preflight_report.txt`.
5. **Валидность INX для настоящего InDesign CS3 не протестирована на самом
   InDesign** — у меня нет доступа к этому приложению. `app/inx/schema.py`
   делает структурную проверку по здравому смыслу (обязательные элементы,
   разумные координаты), но это не официальная XSD-валидация (Adobe её не
   публикует). Каждый архив содержит честное предупреждение об этом в
   `preflight_report.txt` и `README.txt` с инструкцией проверить через
   Preflight-панель самого InDesign перед печатью.

Всё остальное — рабочий, а не заглушечный код: парсинг DOCX, расчёт сетки и
переноса текста, генерация XML через lxml, сборка ZIP, REST API и фронтенд
полностью реализованы и запускаются end-to-end.

## Структура проекта

```
layoutgenius/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── fonts/                 # см. fonts/README.txt
└── app/
    ├── main.py
    ├── config.py
    ├── parser/docx_parser.py
    ├── nlp/keywords.py
    ├── layout/{engine.py,templates.py,fonts.py}
    ├── inx/{generator.py,schema.py}
    ├── preview/renderer.py
    ├── tasks/worker.py
    └── static/{index.html,style.css,script.js}
```
