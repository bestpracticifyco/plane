/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { ExtService } from "../../services/ext.service";

const service = new ExtService();

type Props = { workspaceSlug: string; page: "console" | "approvals" | "attendance" | "time-off" | "dashboards" };

/**
 * Embeds a Governor page in an iframe (FR-EXT-061/064). Plane mints a <=5-minute signed hand-off
 * token; the Governor validates it and starts its own session. If the Governor is unreachable or
 * not configured, a plain message is shown instead of a blank frame.
 */
export const GovernorFrame = observer(function GovernorFrame({ workspaceSlug, page }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mint = useCallback(async () => {
    try {
      const { token, governor_url } = await service.handoff(workspaceSlug);
      if (!governor_url) throw new Error("not configured");
      setSrc(`${governor_url.replace(/\/$/, "")}/embed/${page}?ws=${encodeURIComponent(workspaceSlug)}#token=${token}`);
      setError(null);
    } catch {
      setError("The Governor is not available yet. This page will work once it is deployed.");
    }
  }, [workspaceSlug, page]);

  useEffect(() => {
    void mint();
    const onMessage = (e: MessageEvent) => {
      if (e.origin === window.location.origin && e.data?.type === "ext:token-expired") void mint();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [mint]);

  if (error) return <div className="flex h-full w-full items-center justify-center p-8 text-13 text-secondary">{error}</div>;
  if (!src) return null;
  return <iframe title={`Governor ${page}`} src={src} className="h-full w-full border-0" sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />;
});
