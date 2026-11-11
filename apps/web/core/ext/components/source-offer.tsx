/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

/**
 * AGPL-3.0 §13 source offer (FR-EXT-070): a small, fixed link to this fork's public repository
 * and NOTICE, rendered once in the application shell so it appears on every page.
 */
export function ExtSourceOffer() {
  return (
    <a
      href="https://github.com/bestpracticifyco/plane#readme"
      target="_blank"
      rel="noopener noreferrer"
      title="This instance runs a modified version of Plane (AGPL-3.0). Get the complete source."
      className="fixed right-2 bottom-1 z-[5] text-[10px] text-placeholder opacity-60 hover:text-secondary hover:opacity-100"
    >
      Source (AGPL-3.0)
    </a>
  );
}
