# Django Prometheus Setup

`django-prometheus` is already declared in `requirements/production.txt`. Below are the remaining integration steps.

## 1. INSTALLED_APPS (config/settings/base.py)

Add `django_prometheus` **first** in the `DJANGO_APPS` list, before anything else:

```python
DJANGO_APPS = [
    'django_prometheus',
    'daphne',
    'django.contrib.admin',
    ...
]
```

## 2. MIDDLEWARE (config/settings/base.py)

Add the Prometheus middleware **first** in the `MIDDLEWARE` list, before `corsheaders.middleware.CorsMiddleware`:

```python
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    ...
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]
```

`PrometheusAfterMiddleware` must be the **last** entry in `MIDDLEWARE`.

## 3. Database engine (config/settings/base.py)

Replace the default PostgreSQL engine with the prometheus-wrapped version:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_prometheus.db.backends.postgresql',
        ...
    }
}
```

## 4. URL config (config/urls.py)

Add the metrics endpoint:

```python
urlpatterns = [
    path('metrics/', include('django_prometheus.urls')),
    ...
]
```

## 5. Verify

Start the server and check: `curl http://localhost:8000/metrics/`. You should see a Prometheus-formatted text response with `django_`-prefixed metrics.
