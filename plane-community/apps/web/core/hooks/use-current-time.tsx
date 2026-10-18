/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";

export const useCurrentTime = () => {
  // Do not construct a Date during SSR. The server and browser can be in
  // different time zones and even different minutes, which makes the first
  // client render disagree with the server markup and causes React hydration
  // failures. Both sides start at null, then the browser fills in live time
  // immediately after hydration.
  const [currentTime, setCurrentTime] = useState<Date | null>(null);

  useEffect(() => {
    const updateCurrentTime = () => setCurrentTime(new Date());
    updateCurrentTime();
    const intervalId = setInterval(updateCurrentTime, 60000);

    return () => clearInterval(intervalId);
  }, []);

  return {
    currentTime,
  };
};
