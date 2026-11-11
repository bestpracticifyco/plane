# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Best Practicify overlay settings: production + plane_ext.

Selected with DJANGO_SETTINGS_MODULE=plane.settings.bp (upstream entrypoints use setdefault,
so the environment variable wins without editing any upstream file).
"""

import os

from .production import *  # noqa: F401,F403

INSTALLED_APPS += ["plane.ext"]  # noqa: F405
ROOT_URLCONF = "plane.ext.urls_root"

# Fail closed (FR-EXT-096): refuse to start without the essentials or with upstream placeholders.
_REQUIRED = ["SECRET_KEY", "WEB_URL", "LIVE_SERVER_SECRET_KEY"]
_missing = [k for k in _REQUIRED if not os.environ.get(k)]
if not (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_PASSWORD")):
    _missing.append("DATABASE_URL or POSTGRES_PASSWORD")
if _missing:
    raise RuntimeError(f"plane.settings.bp: missing required environment: {', '.join(_missing)}")
for _k in ("SECRET_KEY", "LIVE_SERVER_SECRET_KEY"):
    if os.environ.get(_k) in {"changeme", "change-this-key-on-deployment", "secret-key"}:
        raise RuntimeError(f"plane.settings.bp: {_k} is an upstream placeholder value")

PLANE_EXT = {
    "HANDOFF_TOKEN_TTL_SECONDS": 300,
    "HANDOFF_SIGNING_KEY": os.environ.get("EXT_HANDOFF_SIGNING_KEY", ""),
    "GOVERNOR_BASE_URL": os.environ.get("GOVERNOR_BASE_URL", ""),
    "SOURCE_REPO_URL": "https://github.com/bestpracticifyco/plane",
    "VERSION": os.environ.get("APP_RELEASE_TAG", "dev"),
}
