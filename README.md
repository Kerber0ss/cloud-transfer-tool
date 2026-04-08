# ☁️ Cloud Transfer

Веб-приложение для переноса файлов из сторонних облачных хранилищ **напрямую в Google Drive** — без скачивания на локальный диск. Файлы стримятся чанками прямо с источника в Google Drive через Resumable Upload API.

> **Сейчас поддерживается:** cloud.mail.ru (публичные ссылки)  
> **В планах:** Mega.nz, Dropbox, Hitfile и другие

---

## Как это работает

```
Браузер → нажал "Start Transfer"
    ↓ POST /api/upload  (возвращает task_id мгновенно)
Celery Worker (фоновый процесс)
    ↓ GET cloud.mail.ru/public/... → httpx stream
    ↓ буфер 8MB в памяти (файл не пишется на диск!)
    ↓ PUT Google Drive Resumable Upload API
    ↓ следующий чанк...
    ✅ Файл появляется в Google Drive
```

**Браузер можно закрыть сразу после старта** — передача идёт в фоне на сервере независимо от клиента. Статус и история сохраняются в Redis на 7 дней.

---

## Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12 + FastAPI |
| Фоновые задачи | Celery 5 + Redis |
| HTTP-клиент | httpx (async streaming) |
| Google Drive | google-api-python-client + google-auth-oauthlib |
| Frontend | React 18 + Vite + TypeScript + shadcn/ui + Tailwind CSS |
| Контейнеризация | Docker + Docker Compose |

---

## Запуск локально

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd cloud-transfer
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Открыть `.env` и заполнить:

```env
APP_USERNAME=admin               # логин для входа в приложение
APP_PASSWORD=your_password       # пароль (минимум 8 символов)
SECRET_KEY=your-random-secret    # случайная строка, см. ниже

GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
FRONTEND_URL=http://localhost:3000

REDIS_URL=redis://redis:6379/0
CELERY_CONCURRENCY=4            # параллельных загрузок одновременно
```

Сгенерировать `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Настроить Google OAuth2

1. Открыть [Google Cloud Console](https://console.cloud.google.com/)
2. Создать проект (или выбрать существующий)
3. Перейти в **APIs & Services → OAuth consent screen**
   - User Type: External
   - Заполнить название приложения и email
4. Перейти в **APIs & Services → Credentials → Create Credentials → OAuth Client ID**
   - Application type: **Web application**
   - Authorized redirect URIs: `http://localhost:8000/api/auth/google/callback`
5. Скопировать **Client ID** и **Client Secret** в `.env`
6. Включить нужные APIs:
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
   - [Google Picker API](https://console.cloud.google.com/apis/library/picker.googleapis.com)

### 4. Запустить

```bash
docker-compose up --build
```

Открыть браузер: **http://localhost:3000**

---

## Запуск на VPS

### Требования к серверу

- **ОС:** Ubuntu 22.04 / Debian 12 / любой Linux
- **RAM:** минимум 1 GB (рекомендуется 2 GB+)
- **Диск:** 10 GB+ (файлы на диск не сохраняются, только образы Docker)
- Открытый порт **3000** (фронтенд) и/или **8000** (API)

### Шаг 1 — Установить Docker на VPS

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Проверить
docker --version
docker-compose --version
```

### Шаг 2 — Загрузить проект на сервер

```bash
# Вариант A: через git
git clone <repo-url> /opt/cloud-transfer
cd /opt/cloud-transfer

# Вариант B: через scp с локального ПК
scp -r ./cloud-transfer user@YOUR_SERVER_IP:/opt/cloud-transfer
```

### Шаг 3 — Настроить .env для VPS

```bash
cd /opt/cloud-transfer
cp .env.example .env
nano .env
```

> ⚠️ Важно: заменить `localhost` на реальный IP или домен сервера:

```env
APP_USERNAME=admin
APP_PASSWORD=your_strong_password
SECRET_KEY=your-random-64-char-secret

GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
GOOGLE_REDIRECT_URI=http://YOUR_SERVER_IP:8000/api/auth/google/callback
FRONTEND_URL=http://YOUR_SERVER_IP:3000

REDIS_URL=redis://redis:6379/0
CELERY_CONCURRENCY=4
```

Также в Google Cloud Console добавить новый Authorized redirect URI:
`http://YOUR_SERVER_IP:8000/api/auth/google/callback`

### Шаг 4 — Запустить в фоне

```bash
cd /opt/cloud-transfer
docker-compose up -d --build
```

Флаг `-d` запускает всё в detached режиме — терминал можно закрыть, сервисы продолжат работать.

### Шаг 5 — Проверить статус

```bash
# Статус контейнеров
docker-compose ps

# Health check
curl http://localhost:8000/health
# Ожидаемый ответ: {"status":"ok","redis":"ok","celery":"ok"}

# Логи в реальном времени
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f worker
docker-compose logs -f backend
```

### Шаг 6 (опционально) — Домен + HTTPS через Nginx

Установить Nginx на хосте:

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

Создать конфиг `/etc/nginx/sites-available/cloud-transfer`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Фронтенд
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API и OAuth callback
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_buffering off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/cloud-transfer /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# SSL сертификат (Let's Encrypt, бесплатно)
sudo certbot --nginx -d your-domain.com
```

После этого обновить `.env`:

```env
GOOGLE_REDIRECT_URI=https://your-domain.com/api/auth/google/callback
FRONTEND_URL=https://your-domain.com
```

И перезапустить:

```bash
docker-compose up -d
```

### Автозапуск после перезагрузки сервера

В `docker-compose.yml` уже стоит `restart: unless-stopped` для всех сервисов. Нужно только включить автозапуск Docker:

```bash
sudo systemctl enable docker
```

После этого при перезагрузке VPS все контейнеры поднимутся автоматически.

---

## Управление на сервере

```bash
# Остановить всё
docker-compose down

# Перезапустить конкретный сервис
docker-compose up -d --build backend worker

# Посмотреть активные задачи Celery
docker-compose exec worker celery -A app.tasks.celery_app inspect active

# Очистить очередь задач (если что-то застряло)
docker-compose exec worker celery -A app.tasks.celery_app purge

# Обновить приложение
git pull
docker-compose up -d --build
```

---

## Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `APP_USERNAME` | Логин для входа в веб-интерфейс | `admin` |
| `APP_PASSWORD` | Пароль для входа | `MyStr0ngPass!` |
| `SECRET_KEY` | Секрет для JWT токенов (мин. 32 символа) | `abc123...` |
| `GOOGLE_CLIENT_ID` | OAuth2 Client ID из Google Console | `xxx.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | OAuth2 Client Secret | `GOCSPX-xxx` |
| `GOOGLE_REDIRECT_URI` | Callback URL после авторизации Google | `http://host:8000/api/auth/google/callback` |
| `FRONTEND_URL` | Адрес фронтенда (для редиректа после OAuth) | `http://host:3000` |
| `REDIS_URL` | Адрес Redis (не менять при работе через Docker) | `redis://redis:6379/0` |
| `CELERY_CONCURRENCY` | Количество параллельных загрузок | `4` |

---

## Сценарий использования

1. Открыть приложение и войти (логин/пароль из `.env`)
2. Нажать **Connect Google Drive** → авторизоваться через Google аккаунт
3. Вставить публичную ссылку из cloud.mail.ru в поле Source URL
4. Нажать **Choose Folder** → выбрать папку назначения через Google Picker
5. Нажать **🚀 Start Transfer**
6. Закрыть браузер если нужно — передача идёт в фоне на сервере
7. Открыть приложение позже → увидеть статус и историю всех передач

---

## Что можно, а что нельзя после старта загрузки

| Действие | Результат |
|----------|-----------|
| Закрыть вкладку браузера | ✅ Загрузка продолжается |
| Закрыть браузер полностью | ✅ Загрузка продолжается |
| Перезагрузить страницу | ✅ История сохранена в Redis |
| Выключить свой ПК | ✅ Загрузка продолжается (если VPS работает) |
| Остановить Docker на сервере | ❌ Загрузка прервётся |
| Перезагрузить VPS | ✅ Docker поднимется автоматически (если включён `systemctl enable docker`) |

---

## Добавление нового провайдера

Архитектура расширяемая. Чтобы добавить, например, Dropbox:

**1. Создать** `backend/app/connectors/dropbox.py`:

```python
from app.connectors.base import BaseConnector, DownloadInfo

class DropboxConnector(BaseConnector):
    async def get_download_info(self, url: str) -> DownloadInfo:
        # Реализовать получение прямого URL из Dropbox-ссылки
        ...
```

**2. Зарегистрировать** в `backend/app/connectors/registry.py`:

```python
from app.connectors.dropbox import DropboxConnector
_CONNECTORS[Provider.DROPBOX] = DropboxConnector
```

**3. Добавить детектор** в `frontend/src/components/UploadForm.tsx`:

```typescript
if (url.includes('dropbox.com')) return { name: 'Dropbox', value: 'dropbox' }
```

---

## Структура проекта

```
cloud-transfer/
├── backend/
│   ├── app/
│   │   ├── auth/
│   │   │   ├── app_auth.py        # JWT авторизация в приложение
│   │   │   └── google_oauth.py    # Google OAuth2 + Redis token storage
│   │   ├── connectors/
│   │   │   ├── base.py            # BaseConnector интерфейс
│   │   │   ├── mailru.py          # cloud.mail.ru коннектор
│   │   │   └── registry.py        # фабрика коннекторов
│   │   ├── services/
│   │   │   └── upload_engine.py   # ключевой модуль: stream → GDrive
│   │   ├── tasks/
│   │   │   ├── celery_app.py      # Celery конфигурация
│   │   │   └── transfer.py        # фоновая задача передачи
│   │   ├── api/
│   │   │   ├── tasks.py           # REST API + SSE прогресс
│   │   │   └── upload.py          # POST /api/upload
│   │   ├── config.py              # pydantic-settings
│   │   ├── models.py              # Pydantic схемы
│   │   └── main.py                # FastAPI app
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/                # shadcn/ui компоненты
│   │   │   ├── UploadForm.tsx     # форма + Google Picker
│   │   │   ├── TaskList.tsx       # история + прогресс-бары
│   │   │   ├── StatsSummary.tsx   # карточки статистики
│   │   │   └── GoogleDriveConnect.tsx
│   │   ├── hooks/
│   │   │   ├── useGoogleDrive.ts  # статус подключения GDrive
│   │   │   └── useTaskProgress.ts # SSE прогресс задачи
│   │   ├── lib/
│   │   │   ├── auth.ts            # JWT утилиты
│   │   │   └── api.ts             # axios + interceptors
│   │   └── pages/
│   │       ├── LoginPage.tsx
│   │       └── DashboardPage.tsx
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```
