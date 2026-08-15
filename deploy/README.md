# Despliegue Portable

La aplicacion se despliega con Docker Compose y Nginx. La misma estructura funciona en una EC2, otra VM Linux o un host con Docker.

## Preparar El Servidor

Instala Docker Engine y Docker Compose Plugin. Crea un usuario de despliegue sin privilegios de root y dale acceso al grupo `docker`.

```bash
sudo usermod -aG docker deploy
mkdir -p /opt/planeacion-api
git clone <URL_DEL_REPOSITORIO> /opt/planeacion-api
```

El archivo `.env` debe existir unicamente en el servidor con permisos `600`. No lo agregues al repositorio.

## Variables De GitHub Actions

Configura estos Repository Secrets:

```text
EC2_HOST
EC2_USER
EC2_SSH_KEY
EC2_DEPLOY_PATH
SECRET_KEY
DATABASE_URL
CORS_ORIGINS
FRONTEND_URL
EMAIL_PROVIDER
EMAIL_SENDER
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_START_TLS
BOOTSTRAP_ADMIN_EMAIL
BOOTSTRAP_ADMIN_PASSWORD
```

`CORS_ORIGINS` debe ser un arreglo JSON, por ejemplo `["https://frontend.example.com"]`. En produccion, `EMAIL_PROVIDER=console` evita enviar correo; cambia a `smtp` unicamente cuando las credenciales esten listas.

## Ejecucion Manual

Desde `backend`:

```bash
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --remove-orphans
curl http://127.0.0.1/health
```

## HTTPS

`deploy/nginx/nginx.conf` funciona como reverse proxy HTTP para validacion inicial. Para produccion, instala un certificado de Let's Encrypt y adapta `nginx.tls.conf.example`, montandolo como `/etc/nginx/nginx.conf`.

El contenedor de la API no publica el puerto al host; solo Nginx queda expuesto. PostgreSQL debe vivir en una red privada o servicio administrado y su URL se entrega mediante `DATABASE_URL`.

## Rollback Operativo

El workflow no borra volumenes de datos. Para volver a una version anterior:

```bash
git checkout <COMMIT_ESTABLE>
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --remove-orphans
```
