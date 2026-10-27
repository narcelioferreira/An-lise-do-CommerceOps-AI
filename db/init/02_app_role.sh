#!/bin/sh
# Cria o usuário da aplicação com privilégio mínimo. Roda uma vez, na criação do volume.
#   olist : somente leitura (dados reais)
#   sim   : leitura e escrita (dados simulados), sem DELETE
#   kb    : somente leitura (a indexação usa o superusuário)
set -eu
: "${APP_DB_USER:?defina APP_DB_USER}"
: "${APP_DB_PASSWORD:?defina APP_DB_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA olist, sim, kb TO :"app_user";
GRANT SELECT ON ALL TABLES IN SCHEMA olist TO :"app_user";
GRANT SELECT ON ALL TABLES IN SCHEMA kb TO :"app_user";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA sim TO :"app_user";
GRANT USAGE ON ALL SEQUENCES IN SCHEMA sim TO :"app_user";
SQL
