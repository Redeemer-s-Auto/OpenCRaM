# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Production settings"""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .common import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get("DEBUG", 0)) == 1

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS += ("plane.garden", "scout_apm.django")  # noqa

GARDEN_AUTH_ENABLED = os.environ.get("GARDEN_AUTH_ENABLED", "0") == "1"
if GARDEN_AUTH_ENABLED:
    garden_origins_raw = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    garden_origins = [origin.strip().rstrip("/") for origin in garden_origins_raw.split(",") if origin.strip()]
    if not garden_origins:
        raise ImproperlyConfigured("Garden mode requires explicit CORS_ALLOWED_ORIGINS")
    if any(not origin.startswith("https://") for origin in garden_origins):
        raise ImproperlyConfigured("Garden production origins must use HTTPS")

    garden_admin_url = os.environ.get("GARDEN_ADMIN_URL", "").strip().rstrip("/")
    if not garden_admin_url or not garden_admin_url.startswith("https://"):
        raise ImproperlyConfigured("Garden mode requires an HTTPS GARDEN_ADMIN_URL")

    parsed_admin_url = urlsplit(garden_admin_url)
    garden_admin_origin = f"{parsed_admin_url.scheme}://{parsed_admin_url.netloc}"
    if not parsed_admin_url.netloc or garden_admin_origin not in garden_origins:
        raise ImproperlyConfigured("The GARDEN_ADMIN_URL origin must be included in CORS_ALLOWED_ORIGINS")

    allowed_hosts_raw = os.environ.get("ALLOWED_HOSTS", "")
    garden_allowed_hosts = [host.strip() for host in allowed_hosts_raw.split(",") if host.strip()]
    if not garden_allowed_hosts or "*" in garden_allowed_hosts:
        raise ImproperlyConfigured("Garden mode requires explicit ALLOWED_HOSTS without wildcard entries")

    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = garden_origins
    CSRF_TRUSTED_ORIGINS = garden_origins
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    # Garden Work is intentionally rendered inside the Garden admin shell on a
    # different HTTPS origin. SameSite=None is required for that embedded
    # session; Secure remains mandatory above.
    SESSION_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SAMESITE = "None"


# Scout Settings
SCOUT_MONITOR = os.environ.get("SCOUT_MONITOR", False)
SCOUT_KEY = os.environ.get("SCOUT_KEY", "")
SCOUT_NAME = "Plane"

LOG_DIR = os.path.join(BASE_DIR, "logs")  # noqa

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "verbose": {"format": "%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s"},
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(levelname)s %(asctime)s %(module)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "INFO",
        },
        "file": {
            "class": "plane.utils.logging.SizedTimedRotatingFileHandler",
            "filename": (
                os.path.join(BASE_DIR, "logs", "plane-debug.log")  # noqa
                if DEBUG
                else os.path.join(BASE_DIR, "logs", "plane-error.log")  # noqa
            ),
            "when": "s",
            "maxBytes": 1024 * 1024 * 1,
            "interval": 1,
            "backupCount": 5,
            "formatter": "json",
            "level": "DEBUG" if DEBUG else "ERROR",
        },
    },
    "loggers": {
        "plane.api.request": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.api": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.worker": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.exception": {
            "level": "DEBUG" if DEBUG else "ERROR",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "plane.external": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.authentication": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.migrations": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.garden": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
