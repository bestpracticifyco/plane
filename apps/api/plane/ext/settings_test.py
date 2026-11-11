# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Test settings for plane_ext: upstream test settings + the ext app."""

from plane.settings.test import *  # noqa: F401,F403

INSTALLED_APPS.append("plane.ext")  # noqa: F405
ROOT_URLCONF = "plane.ext.urls_root"
PLANE_EXT = {
    "HANDOFF_TOKEN_TTL_SECONDS": 300,
    "HANDOFF_SIGNING_KEY": "test-signing-key-not-secret",
    "GOVERNOR_BASE_URL": "https://example.invalid/governor",
    "SOURCE_REPO_URL": "https://github.com/bestpracticifyco/plane",
    "VERSION": "test",
}
