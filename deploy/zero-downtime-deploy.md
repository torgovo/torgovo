# Zero-Downtime Deployment Strategy

> Practical guide for deploying Torgovo without dropping connections or
> interrupting running trading bots.  Written for a single-server production
> environment.

---

## Option 1: Rolling Update (Docker Swarm)

If you run multiple `web` replicas, Docker Swarm can perform a rolling update
so at least one instance stays alive at all times.

**Prerequisites:** A Swarm cluster (even single-node) with the compose file
converted to a stack file.

```bash
# Initialize Swarm (one-time)
docker swarm init

# Deploy as a stack (replaces docker compose up)
docker stack deploy -c docker-compose.yml torgovo

# Roll out a new version with zero downtime
docker service update \
  --image torgovo_web:latest \
  --update-parallelism 1 \
  --update-delay 30s \
  --health-cmd "curl -f http://localhost:8000/ht/" \
  --health-interval 10s \
  --health-retries 3 \
  torgovo_web
```

- `--update-parallelism 1` — one container at a time
- `--update-delay 30s` — wait 30s between each replacement
- Swarm auto-rolls back if the new container fails its health check

**Limitations:** Stateful services (db, redis) cannot be rolled; Celery workers
need manual restart after the web update finishes.

---

## Option 2: Blue-Green with Docker Compose

Run two independent Compose projects side by side, then swap the reverse proxy.

```
Blue (current)     Green (next)
┌──────────────┐   ┌──────────────┐
│  web:8000     │   │  web:8001    │
│  celery-*     │   │  celery-*    │
│  db, redis    │   │  (shared)    │
└──────────────┘   └──────────────┘
       │                  │
       └────── nginx ─────┘
         (upstream swap)
```

### Step-by-step

```bash
# 1. Current live project
docker compose -p torgovo-blue up -d

# 2. Build green
cp docker-compose.yml docker-compose.green.yml
# Edit green → change ports (web:8001), project name
docker compose -p torgovo-green -f docker-compose.green.yml up -d

# 3. Health check green
curl -f http://localhost:8001/ht/ || { echo "Green failed"; docker compose -p torgovo-green down; exit 1; }

# 4. Swap nginx upstream to green (reload without dropping connections)
nginx -s reload

# 5. Tear down blue
docker compose -p torgovo-blue down
```

**Downside:** Requires a separate compose file with altered ports/project name.
The existing `docker-compose.green.yml` already provides this — it adds a
`web-green` service that shares the same network and volumes.

---

## Option 3: Tag-Based Deploy with Health Check Gating (Recommended)

The most practical approach for a single-server setup.  It uses image tags,
Docker Compose, and a health-check loop to gate traffic.

### Workflow

```bash
# 1. Pull or build the new image with a unique tag
docker compose build web
# or: docker compose pull web

# 2. Run migrations (safe — old code still serves requests)
docker compose run --rm web python manage.py migrate --noinput

# 3. Collect static files (new files won't break old code)
docker compose run --rm web python manage.py collectstatic --noinput --clear

# 4. Spin up green alongside blue (using docker-compose.green.yml)
docker compose -f docker-compose.yml -f docker-compose.green.yml up -d --no-deps web-green

# 5. Wait for green to pass its health check
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/ht/ > /dev/null 2>&1; then
    echo "Green healthy after ${i}s"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Health check failed — rolling back"
    docker compose -f docker-compose.yml -f docker-compose.green.yml rm -sf web-green
    exit 1
  fi
  sleep 2
done

# 6. Cut traffic — scale blue down, green to 1
docker compose up -d --no-deps --scale web=0
docker compose -f docker-compose.yml -f docker-compose.green.yml up -d --no-deps --scale web-green=1
docker compose -f docker-compose.yml -f docker-compose.green.yml rm -f web-green

# 7. Restart Celery gracefully
docker compose exec celery-worker celery -A config.celery control shutdown 2>/dev/null || true
docker compose up -d --no-deps celery-worker celery-beat
```

This is exactly what `deploy/deploy.sh` does.  The key insight: the `db` and
`redis` services are never restarted, so connections from running trading bots
are not interrupted.

### Why Option 3 wins

| Concern | Mitigation |
|---------|-----------|
| DB migrations run before cutover | Code is backward-compatible with old schema |
| Static files pre-collected | No race on first request to new container |
| Health check gates traffic | Bad deploy auto-rolls back |
| Celery restarted after cutover | Tasks don't run with mismatched code |
| Single server, no Swarm | Works with plain Docker Compose |

---

## Pre-Deploy Checklist

Run every item **before** starting the deploy:

```bash
# 1. Django deployment check
python manage.py check --deploy

# 2. Review pending migrations
python manage.py migrate --plan

# 3. Run full test suite
python manage.py test --parallel

# 4. Verify environment
docker compose config  # validates compose file
```

Also verify:
- [ ] `.env` has `DJANGO_SECRET_KEY`, `FERNET_KEY`, `JWT_SECRET_KEY` set
- [ ] SSL certificates in `ssl/` are not expired
- [ ] Database backup was taken (run `./deploy/backup.sh`)
- [ ] Redis has enough free memory (`INFO memory`)

---

## Rollback Procedure

### If the new containers are still running

```bash
# Bring back the previous image tag
docker compose up -d --no-deps --scale web=1 web
docker compose up -d --no-deps celery-worker celery-beat

# Revert database (if a migration was applied)
docker compose run --rm web python manage.py migrate <app_name> <previous_migration>
```

### If the deploy script already exited

Restore from the database backup taken in the pre-deploy checklist:

```bash
# 1. Stop all services
docker compose down

# 2. Restore DB
gunzip -c /var/backups/torgovo/torgovo_db_<timestamp>.sql.gz | \
  docker compose run --rm db psql -U postgres torgovo

# 3. Restart with the old tag
docker compose up -d

# 4. Verify
curl -f http://localhost/ht/
```

### Image rollback with tags

If you tag images (`torgovo_web:v20260601`), rollback is a one-liner:

```bash
export TAG=v20260601
docker compose up -d --no-deps web
```

---

## References

- `deploy/deploy.sh` — the automated script implementing Option 3
- `docker-compose.green.yml` — green stack definition
- `deploy/backup.sh` — database backup script
