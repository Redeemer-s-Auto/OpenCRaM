import assert from "node:assert/strict";
import test from "node:test";
import { resolveBrand } from "./brand-config.ts";

test("no theme set keeps the Garden look and ignores brand values", () => {
  const brand = resolveBrand({ VITE_BRAND_NAME: "Shop Notes", VITE_BRAND_LOGO_URL: "https://x.test/logo.png" });
  assert.equal(brand.theme, "garden");
  assert.equal(brand.isHub, false);
  assert.equal(brand.logoUrl, "");
  assert.equal(brand.productName, "Garden Work");
});

test("unknown theme values fall back to garden", () => {
  assert.equal(resolveBrand({ VITE_BRAND_THEME: "purple" }).theme, "garden");
});

test("hub theme reads name, logo and icon", () => {
  const brand = resolveBrand({
    VITE_BRAND_THEME: " HUB ",
    VITE_BRAND_NAME: " Shop Notes ",
    VITE_BRAND_LOGO_URL: "https://hub.test/logo.png",
  });
  assert.equal(brand.theme, "hub");
  assert.equal(brand.name, "Shop Notes");
  assert.equal(brand.logoUrl, "https://hub.test/logo.png");
  assert.equal(brand.iconUrl, "https://hub.test/logo.png", "icon falls back to the logo");
  assert.equal(brand.productName, "Shop Notes");
});

test("hub theme accepts a same-site path and rejects unsafe URLs", () => {
  assert.equal(
    resolveBrand({ VITE_BRAND_THEME: "hub", VITE_BRAND_LOGO_URL: "/brand/logo.svg" }).logoUrl,
    "/brand/logo.svg"
  );
  assert.equal(resolveBrand({ VITE_BRAND_THEME: "hub", VITE_BRAND_LOGO_URL: "javascript:alert(1)" }).logoUrl, "");
  assert.equal(resolveBrand({ VITE_BRAND_THEME: "hub", VITE_BRAND_LOGO_URL: "//evil.test/x.png" }).logoUrl, "");
});

test("hub product name falls back to the app name, then Notes", () => {
  assert.equal(resolveBrand({ VITE_BRAND_THEME: "hub" }, "Shop Notes App").productName, "Shop Notes App");
  assert.equal(resolveBrand({ VITE_BRAND_THEME: "hub" }).productName, "Notes");
});
