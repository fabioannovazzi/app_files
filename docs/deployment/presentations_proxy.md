# Presentations reverse proxy configuration

Access to `/presentations/**` needs to traverse FastAPI so the permission
structure checks can run before any file is served. Disable previous CDN or
static-site rules that read the directory directly and forward every request to
the API workers.

## Nginx

```nginx
upstream fastapi_app {
    server 127.0.0.1:8000;  # or your Gunicorn/Uvicorn upstream
}

server {
    listen 443 ssl;
    server_name example.com;

    location /presentations/ {
        proxy_pass http://fastapi_app;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_intercept_errors on;
    }

    # other locations (/, /static, etc.) remain unchanged
}
```

Remove any earlier `alias /var/www/presentations` or `root` block that exposed
files directly.

## Apache HTTPD

```apache
ProxyPreserveHost On
ProxyPassMatch ^/presentations/(.*)$ http://fastapi_app/presentations/$1
ProxyPassReverse /presentations/ http://fastapi_app/presentations/
```

Make sure `mod_proxy` and `mod_proxy_http` are enabled and that no `Alias
/presentations/` directive remains.

## CloudFront / CDN

* Remove behaviours pointing `/presentations/*` to S3 or static origins.
* Add a behaviour that forwards all methods and headers for the
  `/presentations/*` path pattern to the FastAPI origin.
* Enable caching disabled or set TTL to 0 so permissions are checked every time.

## Worker access to the presentations directory

The FastAPI router reads files from `presentations/` after permissions succeed.
Mount that directory into every worker container (read-only) so
`FileResponse` can stream the deck:

```yaml
services:
  api:
    volumes:
      - ./presentations:/app/presentations:ro
```

For VM-based deployments, copy or mount the directory at the same path that the
application expects (`$APP_HOME/presentations`).
