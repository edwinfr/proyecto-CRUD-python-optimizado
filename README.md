# CRUD de empleados con Flask

## Despliegue en Clever Cloud

1. Crea una aplicación de tipo **Python** y vincúlale el add-on MySQL.
2. En **Environment variables** de la aplicación configura:
   - `CC_PYTHON_VERSION=3.12`
   - `CC_PYTHON_MODULE=app:app`
   - `CC_PYTHON_BACKEND=gunicorn`
   - `CC_HEALTH_CHECK_PATH=/health`
3. Importa `empleados.sql` en la base de datos vinculada.
4. Sube este repositorio a GitHub y vuelve a desplegar desde Clever Cloud.

La aplicación toma automáticamente `MYSQL_ADDON_HOST`, `MYSQL_ADDON_PORT`,
`MYSQL_ADDON_USER`, `MYSQL_ADDON_PASSWORD` y `MYSQL_ADDON_DB`, inyectadas por
Clever Cloud al vincular el add-on. Para desarrollo local, define
`DATABASE_URL` a partir de `.env.example`.
