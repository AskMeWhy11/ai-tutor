#!/usr/bin/env bash
# Первичная выдача сертификата Let's Encrypt для домена.
# Использование: ./deploy/scripts/init-letsencrypt.sh
set -euo pipefail

DOMAIN="${DOMAIN:-fppzo.ru}"
EMAIL="${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL not set}"
STAGING="${STAGING:-0}"

CERT_DIR="./deploy/certbot/conf"
WEBROOT="./deploy/certbot/www"

mkdir -p "$CERT_DIR" "$WEBROOT"

# Скачиваем рекомендованные TLS-параметры (если ещё нет)
if [ ! -e "$CERT_DIR/options-ssl-nginx.conf" ]; then
    curl -fsSL https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "$CERT_DIR/options-ssl-nginx.conf"
fi
if [ ! -e "$CERT_DIR/ssl-dhparams.pem" ]; then
    curl -fsSL https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "$CERT_DIR/ssl-dhparams.pem"
fi

# Заглушка сертификата (чтобы nginx стартовал)
LIVE_DIR="$CERT_DIR/live/$DOMAIN"
mkdir -p "$LIVE_DIR"
docker run --rm -v "$(pwd)/$CERT_DIR:/etc/letsencrypt" \
    --entrypoint /bin/sh certbot/certbot -c "\
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
      -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
      -subj '/CN=localhost'"

docker compose up -d nginx

# Удаляем заглушку и запрашиваем настоящий сертификат
docker compose run --rm --entrypoint "\
    rm -rf /etc/letsencrypt/live/$DOMAIN \
    /etc/letsencrypt/archive/$DOMAIN \
    /etc/letsencrypt/renewal/$DOMAIN.conf" certbot

STAGING_ARG=""
if [ "$STAGING" != "0" ]; then STAGING_ARG="--staging"; fi

docker compose run --rm --entrypoint "\
    certbot certonly --webroot -w /var/www/certbot \
    $STAGING_ARG \
    --email $EMAIL \
    -d $DOMAIN -d www.$DOMAIN \
    --rsa-key-size 2048 \
    --agree-tos --no-eff-email --force-renewal" certbot

docker compose exec nginx nginx -s reload
echo "Готово. Сертификат выдан для $DOMAIN."
