import test from "node:test";
import { strict as assert } from "node:assert";

import { clampDecimals, formatUnits, parseUnits } from "../src/utils/amounts";

test("clampDecimals stays within pragmatic bounds", () => {
  assert.equal(clampDecimals(-5), 0);
  assert.equal(clampDecimals(18), 18);
  assert.equal(clampDecimals(999), 36);
});

test("parseUnits handles whole and fractional values deterministically", () => {
  const a = parseUnits("1.25", 6);
  assert.equal(a.ok, true);
  assert.equal(a.raw, "1250000");
  assert.equal(a.truncated, false);

  const b = parseUnits("0.123456789", 6);
  assert.equal(b.ok, true);
  assert.equal(b.raw, "123456");
  assert.equal(b.truncated, true);
});

test("formatUnits renders compact fractional output", () => {
  assert.equal(formatUnits("1250000", 6), "1.25");
  assert.equal(formatUnits("1000000", 6), "1");
  assert.equal(formatUnits("0", 18), "0");
});
