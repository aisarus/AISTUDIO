# 🎨 AI Scene Studio

Мобильное веб-приложение для AI-художников. Генерация и компоновка слоёв через Gemini (Nano Banana).

## Возможности

- **Генерация сцены** — из одного промпта создаётся 4 слоя: объект, фон, свет, combo
- **Загрузка фото** — импорт из галереи/камеры как слой
- **AI инструменты** — замена фона, освещение, редактирование объекта, удаление, стилизация, цветокоррекция
- **Drag & Drop мёрдж** — перетащить слой на другой → AI объединит их
- **Версирование** — Undo до 12 шагов на каждый слой
- **Мобильный first** — работает на любом смартфоне

## Деплой на Render

### 1. GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR/ai-scene-studio.git
git push -u origin main
```

### 2. Render

1. Открыть [render.com](https://render.com) → New → Web Service
2. Подключить GitHub репозиторий
3. Render автоматически найдёт `render.yaml`
4. Deploy → готово

Либо нажать кнопку:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## Локальный запуск

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# открыть http://localhost:8000
```

## Стек

- **Backend**: FastAPI + Uvicorn
- **AI**: Google Gemini (`gemini-2.5-flash-image` для картинок, `gemini-2.0-flash` для текста)
- **Frontend**: Vanilla JS SPA, мобильный mobile-first дизайн
- **Deploy**: Render (free tier)

## Структура

```
ai-scene-studio/
├── main.py           # FastAPI backend, все API endpoints
├── requirements.txt
├── render.yaml       # Render deploy config
└── static/
    └── index.html    # Полное SPA приложение
```
