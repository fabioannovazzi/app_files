# PDP Postgres Quick Queries

These snippets inspect the configured PDP Postgres database. Run them from the repo
root with the virtual environment activated.

## Verify Connection

```bash
psql "$PDP_DATABASE_URL" -c 'SELECT 1;'
```

## Count Overall Parents And Variants

```bash
python - <<'PY'
import psycopg

from modules.pdp.postgres_compat import pdp_postgres_url_from_env
from modules.utilities.secrets_loader import load_env_from_secrets_file

load_env_from_secrets_file()
with psycopg.connect(pdp_postgres_url_from_env()) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM parent_products")
        print("parents", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM variants")
        print("variants", cur.fetchone()[0])
PY
```

## Run Direct SQL

```bash
python - <<'PY'
import psycopg

from modules.pdp.postgres_compat import pdp_postgres_url_from_env
from modules.utilities.secrets_loader import load_env_from_secrets_file

load_env_from_secrets_file()
with psycopg.connect(pdp_postgres_url_from_env()) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT retailer, COUNT(*)
            FROM parent_products
            GROUP BY retailer
            ORDER BY COUNT(*) DESC
        """)
        for row in cur.fetchall():
            print(row)
PY
```
