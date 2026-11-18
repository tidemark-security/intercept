import { Buffer } from "node:buffer";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path, { dirname } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(dirname(fileURLToPath(import.meta.url)), "..");
const indexHtml = readFileSync(path.join(frontendRoot, "index.html"), "utf8");
const faviconSvg = readFileSync(path.join(frontendRoot, "public", "favicon.svg"), "utf8");
const tmsLogoSvg = readFileSync(path.join(frontendRoot, "src", "assets", "TMS-logo-green.svg"), "utf8");

function iconHref(linkTag) {
  return linkTag.match(/\bhref=["']([^"']+)["']/i)?.[1] ?? null;
}

test("index.html advertises a root-relative favicon asset that exists", () => {
  const iconLinks =
    indexHtml.match(/<link\b[^>]*\brel=["'][^"']*\bicon\b[^"']*["'][^>]*>/gi) ?? [];
  assert.ok(iconLinks.length > 0, "expected at least one favicon link in index.html");

  for (const link of iconLinks) {
    const href = iconHref(link);

    assert.ok(href, `favicon link is missing href: ${link}`);
    assert.ok(href.startsWith("/") && !href.startsWith("//"), `${href} must resolve from site root`);
    assert.doesNotMatch(href, /(?:^|\/)\.\.(?:\/|$)/, `${href} must not escape the public root`);

    const publicAsset = path.join(frontendRoot, "public", href.slice(1));
    assert.ok(existsSync(publicAsset), `${href} must exist under frontend/public`);
  }
});

test("favicon uses the TMS green logo on a black background", () => {
  assert.match(
    faviconSvg,
    /<rect\b(?=[^>]*\bwidth=["']200["'])(?=[^>]*\bheight=["']200["'])(?=[^>]*\bfill=["']#000000["'])/i,
    "favicon must paint a black background"
  );

  const logoImage = faviconSvg.match(
    /<image\b[^>]*\bhref=["']data:image\/svg\+xml;base64,([^"']+)["']/i
  );
  assert.ok(logoImage, "favicon must embed TMS-logo-green.svg as an SVG image");

  const embeddedLogo = Buffer.from(logoImage[1], "base64").toString("utf8");
  assert.equal(embeddedLogo, tmsLogoSvg, "favicon must embed the checked-in TMS-logo-green.svg");
});
