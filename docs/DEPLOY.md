# Деплой на VPS (Ubuntu 24.04)

## 0. DNS

В панели регистратора `fppzo.ru`:
- `A    @     <IP VPS>`
- `A    www   <IP VPS>`

Проверка: `dig +short fppzo.ru` → IP сервера.

## 1. Подготовка сервера

```bash
ssh root@<IP>

# Создать пользователя
adduser deploy
usermod -aG sudo deploy

# Docker
apt update && apt upgrade -y
apt install -y ca-certificates curl gnupg git ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy

# Firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
