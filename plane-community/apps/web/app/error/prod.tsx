/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTheme } from "next-themes";
import { Button } from "@plane/propel/button";
import maintenanceModeDarkModeImage from "@/app/assets/instance/maintenance-mode-dark.svg?url";
import maintenanceModeLightModeImage from "@/app/assets/instance/maintenance-mode-light.svg?url";
import gardenMark from "@/app/assets/garden-mark.svg?url";
import DefaultLayout from "@/layouts/default-layout";

import { gardenAdminName, gardenAppName, gardenMode } from "@/lib/garden-config";

const linkMap = [
  {
    key: "mail_to",
    label: "Contact Support",
    value: "mailto:support@plane.so",
  },
  {
    key: "status",
    label: "Status Page",
    value: "https://status.plane.so/",
  },
  {
    key: "twitter_handle",
    label: "@planepowers",
    value: "https://x.com/planepowers",
  },
];

interface ProdErrorComponentProps {
  onGoHome: () => void;
}

export function ProdErrorComponent({ onGoHome }: ProdErrorComponentProps) {
  const { resolvedTheme } = useTheme();
  const maintenanceModeImage = resolvedTheme === "dark" ? maintenanceModeDarkModeImage : maintenanceModeLightModeImage;

  if (gardenMode) {
    return (
      <DefaultLayout>
        <div className="relative container mx-auto flex h-full w-full max-w-xl flex-col items-center justify-center gap-6 bg-surface-1 px-6 text-center">
          <img src={gardenMark} className="h-20 w-20 object-contain" alt={gardenAppName} />
          <div className="flex flex-col gap-2">
            <h1 className="text-18 font-semibold text-primary">{gardenAppName} hit a snag</h1>
            <p className="text-14 font-medium text-secondary">
              Try refreshing the page. If the problem continues, return to {gardenAdminName} and try again.
            </p>
          </div>
          <Button variant="primary" size="lg" onClick={onGoHome}>
            Go to Work home
          </Button>
        </div>
      </DefaultLayout>
    );
  }

  return (
    <DefaultLayout>
      <div className="relative container mx-auto flex h-full w-full max-w-xl flex-col items-center justify-center gap-2 gap-y-6 bg-surface-1 px-6 text-center">
        <div className="relative w-full">
          <img
            src={maintenanceModeImage}
            height="176"
            width="288"
            alt="ProjectSettingImg"
            className="h-full w-full object-fill object-center"
          />
        </div>
        <div className="relative mt-4 flex w-full flex-col gap-4">
          <div className="flex flex-col gap-2.5">
            <h1 className="text-left text-18 font-semibold text-primary">&#x1F6A7; Looks like something went wrong!</h1>
            <span className="text-left text-14 font-medium text-secondary">
              We track these errors automatically and working on getting things back up and running. If the problem
              persists feel free to contact us. In the meantime, try refreshing.
            </span>
          </div>

          <div className="mt-1 flex items-center justify-start gap-6">
            {linkMap.map((link) => (
              <div key={link.key}>
                <a
                  href={link.value}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-13 text-accent-primary hover:underline"
                >
                  {link.label}
                </a>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-start gap-6">
            <Button variant="primary" size="lg" onClick={onGoHome}>
              Go to home
            </Button>
          </div>
        </div>
      </div>
    </DefaultLayout>
  );
}
