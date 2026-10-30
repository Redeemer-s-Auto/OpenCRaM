/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useEffect, useState } from "react";

/** Below Tailwind's `md` breakpoint: a phone, or a narrow window. */
const PHONE_QUERY = "(max-width: 767px)";

/**
 * True while the viewport is phone-sized. Unlike usePlatformOS (user agent), this follows the
 * window size, so a narrow desktop window gets the phone layout too and the real phone layout
 * can be checked on a computer.
 */
export const usePhoneViewport = (): boolean => {
  const [isPhone, setIsPhone] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia(PHONE_QUERY).matches
  );

  useEffect(() => {
    const query = window.matchMedia(PHONE_QUERY);
    const onChange = (event: MediaQueryListEvent) => setIsPhone(event.matches);
    setIsPhone(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return isPhone;
};
