"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const amounts_1 = require("../src/utils/amounts");
(0, node_test_1.default)("clampDecimals stays within pragmatic bounds", () => {
    node_assert_1.strict.equal((0, amounts_1.clampDecimals)(-5), 0);
    node_assert_1.strict.equal((0, amounts_1.clampDecimals)(18), 18);
    node_assert_1.strict.equal((0, amounts_1.clampDecimals)(999), 36);
});
(0, node_test_1.default)("parseUnits handles whole and fractional values deterministically", () => {
    const a = (0, amounts_1.parseUnits)("1.25", 6);
    node_assert_1.strict.equal(a.ok, true);
    node_assert_1.strict.equal(a.raw, "1250000");
    node_assert_1.strict.equal(a.truncated, false);
    const b = (0, amounts_1.parseUnits)("0.123456789", 6);
    node_assert_1.strict.equal(b.ok, true);
    node_assert_1.strict.equal(b.raw, "123456");
    node_assert_1.strict.equal(b.truncated, true);
});
(0, node_test_1.default)("formatUnits renders compact fractional output", () => {
    node_assert_1.strict.equal((0, amounts_1.formatUnits)("1250000", 6), "1.25");
    node_assert_1.strict.equal((0, amounts_1.formatUnits)("1000000", 6), "1");
    node_assert_1.strict.equal((0, amounts_1.formatUnits)("0", 18), "0");
});
