# Hoplite Unified Proxy Gateway

OpenAI-совместимый прокси-шлюз с ротацией ключей, дашбордом и авто-восстановлением.

## Быстрый старт

```bash
cd /tmp/hoplite-gateway
./start.sh
```

Дашборд: http://127.0.0.1:8090/

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус шлюза |
| GET | `/v1/models` | Список моделей (прокси на Hoplite) |
| POST | `/v1/chat/completions` | Чат-комплишн (прокси на Hoplite) |
| GET | `/api/keys` | Список ключей |
| POST | `/api/keys` | Добавить ключ |
| DELETE | `/api/keys/{id}` | Удалить ключ |
| POST | `/api/keys/{id}/test` | Проверить ключ |
| GET | `/api/cards` | Список карт |
| GET | `/api/github` | GitHub аккаунты |
| GET | `/api/stats` | Статистика |
| GET | `/api/events` | SSE-поток событий |
| GET | `/api/settings` | Настройки |

## Ротация ключей

- Round-robin по живым ключам
- 3 попытки с exponential backoff перед пометкой "dead"
- Авто-восстановление: мёртвые ключи перепроверяются
- 401/403 → мгновенная пометка dead

## Системный сервис

```bash
sudo systemctl enable --now hoplite-gateway
sudo systemctl status hoplite-gateway
```

## Структура

```
hoplite-gateway/
├── server.py          # FastAPI-сервер
├── static/
│   └── index.html     # Дашборд (dark theme)
├── data/
│   └── store.json     # Ключи, карты, GitHub, настройки
├── autoreg.py         # Авто-регистрация (Playwright)
├── requirements.txt
├── start.sh
└── hoplite-gateway.service
```

## Порты в системе

| Порт | Сервис |
|------|--------|
| 8090 | Hoplite Gateway (этот) |
| 8080 | Opus Gateway (Sentinel) |
| 8081 | Hoplite Proxy v5 |
| 20128 | OmniRoute |