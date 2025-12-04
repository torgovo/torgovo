# Implementation Plan - Enable and Migrate All Apps

## Goal
Enable all Django apps, register their models in the admin panel, and ensure database migrations are applied.

## Proposed Changes

### Configuration
#### [MODIFY] [base.py](file:///d:/Projects/torgovo2/config/settings/base.py)
- Add `apps.investments` and `apps.referrals` to `LOCAL_APPS`.

#### [MODIFY] [urls.py](file:///d:/Projects/torgovo2/config/urls.py)
- Uncomment all API path includes.

### Admin Registration
Check and update `admin.py` for the following apps to ensure all models are registered:
- `apps.authentication`
- `apps.bots`
- `apps.exchanges`
- `apps.investments`
- `apps.payments`
- `apps.referrals`
- `apps.subscriptions`
- `apps.users`
- `apps.webhooks`

I will use a script to auto-generate `admin.py` content if it's missing or incomplete, ensuring all models found in [models.py](file:///d:/Projects/torgovo2/core/models.py) are registered.

## Verification Plan

### Automated Verification
- Run `python manage.py check` to ensure no configuration errors.
- Run `python manage.py makemigrations` and `python manage.py migrate` to apply changes.

### Manual Verification
- Start the server (`python manage.py runserver`).
- Log in to the admin panel (`http://localhost:8000/admin/`).
- Verify that all apps and their models are listed and accessible.
