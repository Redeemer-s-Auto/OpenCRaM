import assert from "node:assert/strict";
import test from "node:test";
import { isGardenManagedProfileTab } from "./garden-profile-policy.ts";

test("Garden owns identity and authentication while Work keeps its own preferences", () => {
  for (const tab of ["general", "security"]) assert.equal(isGardenManagedProfileTab(true, tab), true);
  for (const tab of ["preferences", "notifications", "api-tokens"]) assert.equal(isGardenManagedProfileTab(true, tab), false);
});
test("ordinary Plane installations retain every account settings page", () => {
  for (const tab of ["general", "security", "preferences", "notifications", "api-tokens"]) {
    assert.equal(isGardenManagedProfileTab(false, tab), false);
  }
});
