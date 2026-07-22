# TheVerum v1

Запускаемая основа русского сервиса независимой аутентификации предметов роскоши.

## Реализовано
- русский публичный сайт;
- публичная проверка сертификата;
- минималистичная страница сертификата;
- PDF-сертификат на одной странице;
- краткий PDF-отчет без клиентского чек-листа из десятков пунктов;
- контекстная работа с серийными номерами, NFC, QR и отсутствующими идентификаторами;
- административный вход;
- создание завершенной проверки;
- выпуск, скачивание и отзыв сертификата;
- PostgreSQL, Redis и MinIO в Docker Compose;
- аудит ключевых административных действий;
- API чтения статуса сертификата.

## Запуск
```bash
cp .env.example .env
# Обязательно замените пароли и SECRET_KEY
docker compose up -d --build
```
Сайт: https://theverum.ru

Демо-сертификат: https://theverum.ru/v/demo-certificate

Админ: значения ADMIN_EMAIL и ADMIN_PASSWORD из `.env`.

## Домен и HTTPS
На сервере с уже работающим `docker compose` (порт 8080):

```bash
cd ~/theverum
git pull
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx-theverum.ru.conf /etc/nginx/sites-available/theverum.ru
sudo ln -sf /etc/nginx/sites-available/theverum.ru /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d theverum.ru -d www.theverum.ru
```

В `.env` на сервере выставьте:
```
APP_URL=https://theverum.ru
COOKIE_SECURE=true
```
После правки: `docker compose up -d`

## Важно
Это рабочая основа v1, а не автоматически сертифицированная production-система. Перед реальным запуском требуется внешний аудит безопасности, юридическая проверка документов, настройка HTTPS, резервного копирования и политики хранения персональных данных.
