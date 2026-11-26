"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.analyticsDashboards = exports.blockspaceState = exports.governanceState = exports.verifyReplay = exports.replayBundle = exports.sampleRftEpisodes = exports.stressEvaluate = exports.metaApply = exports.metaCandidates = exports.exportRftEpisodes = exports.setWealthGoal = exports.fetchWealthGoal = exports.setTreasuryGoal = exports.fetchTreasuryGoal = exports.treasuryState = exports.behaveagentState = exports.consensusState = exports.convertWithdrawExecute = exports.convertWithdrawPrepare = exports.convertWithdrawQuote = exports.withdrawAllExecute = exports.withdrawAllPreview = exports.withdrawAllConfig = exports.withdrawAllState = exports.withdrawExecute = exports.withdrawPrepare = exports.withdrawConfig = exports.multichainSettings = exports.multichainSummary = exports.multichainState = exports.selectChain = exports.fetchChains = exports.applyPreset = exports.getPreset = exports.listPresets = exports.pnlIncome = exports.pnlSummary = exports.gasPresets = exports.adminState = exports.simulateOpportunity = exports.tradeOpportunity = exports.setSafety = exports.setSettings = exports.stopRuntime = exports.startRuntime = exports.fetchState = exports.deployInfo = exports.health = exports.apiPost = exports.apiGet = void 0;
exports.launchFamilyDetail = exports.quarantineLaunchFamily = exports.revertLaunchFamily = exports.pauseLaunchFamily = exports.enableNextFamily = exports.setLaunchMode = exports.launchState = exports.executionQuality = exports.saveRpcPreferences = exports.rpcPreferences = exports.txReceipt = void 0;
const url_1 = require("./url");
function headers(adminKey) {
    const h = {};
    if (adminKey)
        h["X-Admin-Key"] = adminKey;
    return h;
}
// Low-level helpers used by the Sovereign Command Center layer.
// Additive exports: existing screen API calls remain unchanged.
async function apiGet(baseUrl, path, extraHeaders) {
    const url = `${(0, url_1.normalizeBaseUrl)(baseUrl)}${path}`;
    const r = await fetch(url, { headers: { ...(extraHeaders ?? {}) } });
    if (!r.ok)
        throw new Error(`HTTP ${r.status}`);
    return (await r.json());
}
exports.apiGet = apiGet;
async function apiPost(baseUrl, path, body, extraHeaders) {
    const url = `${(0, url_1.normalizeBaseUrl)(baseUrl)}${path}`;
    const r = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json", ...(extraHeaders ?? {}) },
        body: JSON.stringify(body ?? {}),
    });
    if (!r.ok)
        throw new Error(`HTTP ${r.status}`);
    return (await r.json());
}
exports.apiPost = apiPost;
async function jget(url, adminKey) {
    const r = await fetch(url, { headers: headers(adminKey) });
    if (!r.ok)
        throw new Error(`HTTP ${r.status}`);
    return (await r.json());
}
async function jpost(url, body, adminKey) {
    const h = { "content-type": "application/json", ...headers(adminKey) };
    const r = await fetch(url, { method: "POST", headers: h, body: JSON.stringify(body ?? {}) });
    if (!r.ok)
        throw new Error(`HTTP ${r.status}`);
    return (await r.json());
}
// -------------------------
// Core
// -------------------------
async function health(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/health`, adminKey);
}
exports.health = health;
async function deployInfo(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/deploy/info`, adminKey);
}
exports.deployInfo = deployInfo;
async function fetchState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/state`, adminKey);
}
exports.fetchState = fetchState;
async function startRuntime(baseUrl, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/runtime/start`, {}, adminKey);
}
exports.startRuntime = startRuntime;
async function stopRuntime(baseUrl, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/runtime/stop`, {}, adminKey);
}
exports.stopRuntime = stopRuntime;
async function setSettings(baseUrl, patch, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/settings`, patch, adminKey);
}
exports.setSettings = setSettings;
async function setSafety(baseUrl, patch, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/safety`, patch, adminKey);
}
exports.setSafety = setSafety;
async function tradeOpportunity(baseUrl, id, adminKey, amountInOverride) {
    const body = { id };
    if (amountInOverride !== undefined && amountInOverride !== null)
        body.amount_in_override = String(amountInOverride);
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/opportunities/trade`, body, adminKey);
}
exports.tradeOpportunity = tradeOpportunity;
async function simulateOpportunity(baseUrl, id, adminKey, amountInOverride) {
    const body = { id };
    if (amountInOverride !== undefined && amountInOverride !== null)
        body.amount_in_override = String(amountInOverride);
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/opportunities/simulate`, body, adminKey);
}
exports.simulateOpportunity = simulateOpportunity;
async function adminState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/admin/state`, adminKey);
}
exports.adminState = adminState;
async function gasPresets(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/gas/presets`, adminKey);
}
exports.gasPresets = gasPresets;
async function pnlSummary(baseUrl, window = 50, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/pnl/summary?window=${window}`, adminKey);
}
exports.pnlSummary = pnlSummary;
async function pnlIncome(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/pnl/income`, adminKey);
}
exports.pnlIncome = pnlIncome;
// -------------------------
// Presets / chain switching
// -------------------------
async function listPresets(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/presets`, adminKey);
}
exports.listPresets = listPresets;
async function getPreset(baseUrl, chain, name, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/presets/${chain}/${name}`, adminKey);
}
exports.getPreset = getPreset;
async function applyPreset(baseUrl, chain, name, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/presets/apply`, { chain, name, auto_start: true }, adminKey);
}
exports.applyPreset = applyPreset;
async function fetchChains(baseUrl) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/multichain/chains`);
}
exports.fetchChains = fetchChains;
async function selectChain(baseUrl, chain, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/multichain/select`, { chain }, adminKey);
}
exports.selectChain = selectChain;
async function multichainState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/multichain/state`, adminKey);
}
exports.multichainState = multichainState;
async function multichainSummary(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/multichain/summary`, adminKey);
}
exports.multichainSummary = multichainSummary;
async function multichainSettings(baseUrl, patch, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/multichain/settings`, patch, adminKey);
}
exports.multichainSettings = multichainSettings;
// -------------------------
// Withdraw (executor)
// -------------------------
async function withdrawConfig(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/config`, adminKey);
}
exports.withdrawConfig = withdrawConfig;
async function withdrawPrepare(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/prepare`, req, adminKey);
}
exports.withdrawPrepare = withdrawPrepare;
async function withdrawExecute(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/execute`, req, adminKey);
}
exports.withdrawExecute = withdrawExecute;
async function withdrawAllState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/all/state`, adminKey);
}
exports.withdrawAllState = withdrawAllState;
async function withdrawAllConfig(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/all/config`, req, adminKey);
}
exports.withdrawAllConfig = withdrawAllConfig;
async function withdrawAllPreview(baseUrl, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/all/preview`, {}, adminKey);
}
exports.withdrawAllPreview = withdrawAllPreview;
async function withdrawAllExecute(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/all/execute`, req, adminKey);
}
exports.withdrawAllExecute = withdrawAllExecute;
// -------------------------
// Convert + Withdraw (executor)
// -------------------------
async function convertWithdrawQuote(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/convert/quote`, req, adminKey);
}
exports.convertWithdrawQuote = convertWithdrawQuote;
async function convertWithdrawPrepare(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/convert/prepare`, req, adminKey);
}
exports.convertWithdrawPrepare = convertWithdrawPrepare;
async function convertWithdrawExecute(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/convert/execute`, req, adminKey);
}
exports.convertWithdrawExecute = convertWithdrawExecute;
// -------------------------
// Observability / analytics (read-only)
// -------------------------
async function consensusState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/consensus/state`, adminKey);
}
exports.consensusState = consensusState;
async function behaveagentState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/behaveagent/state`, adminKey);
}
exports.behaveagentState = behaveagentState;
async function treasuryState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/treasury/state`, adminKey);
}
exports.treasuryState = treasuryState;
async function fetchTreasuryGoal(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/treasury/goal`, adminKey);
}
exports.fetchTreasuryGoal = fetchTreasuryGoal;
async function setTreasuryGoal(baseUrl, patch, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/treasury/goal`, patch, adminKey);
}
exports.setTreasuryGoal = setTreasuryGoal;
async function fetchWealthGoal(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/wealth/goal`, adminKey);
}
exports.fetchWealthGoal = fetchWealthGoal;
async function setWealthGoal(baseUrl, patch, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/wealth/goal`, patch, adminKey);
}
exports.setWealthGoal = setWealthGoal;
async function exportRftEpisodes(baseUrl, req, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/rft/episodes/export`, req, adminKey);
}
exports.exportRftEpisodes = exportRftEpisodes;
async function metaCandidates(baseUrl, limit = 10, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/meta/candidates?limit=${encodeURIComponent(String(limit))}`, adminKey);
}
exports.metaCandidates = metaCandidates;
async function metaApply(baseUrl, id, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/meta/apply`, { id }, adminKey);
}
exports.metaApply = metaApply;
async function stressEvaluate(baseUrl, scenario, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/stress/evaluate`, { scenario }, adminKey);
}
exports.stressEvaluate = stressEvaluate;
async function sampleRftEpisodes(baseUrl, limit = 5, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/rft/episodes/sample?limit=${encodeURIComponent(String(limit))}`, adminKey);
}
exports.sampleRftEpisodes = sampleRftEpisodes;
async function replayBundle(baseUrl, eventId, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/rft/replay/bundle/${encodeURIComponent(eventId)}`, adminKey);
}
exports.replayBundle = replayBundle;
async function verifyReplay(baseUrl, body, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/rft/replay/verify`, body, adminKey);
}
exports.verifyReplay = verifyReplay;
async function governanceState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/governance/state`, adminKey);
}
exports.governanceState = governanceState;
async function blockspaceState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/blockspace/state`, adminKey);
}
exports.blockspaceState = blockspaceState;
async function analyticsDashboards(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/analytics/dashboards`, adminKey);
}
exports.analyticsDashboards = analyticsDashboards;
async function txReceipt(baseUrl, txHash, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/tx/receipt`, { tx_hash: txHash }, adminKey);
}
exports.txReceipt = txReceipt;
async function rpcPreferences(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/system/rpc/preferences`, adminKey);
}
exports.rpcPreferences = rpcPreferences;
async function saveRpcPreferences(baseUrl, body, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/system/rpc/preferences`, body, adminKey);
}
exports.saveRpcPreferences = saveRpcPreferences;
async function executionQuality(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/system/execution/quality`, adminKey);
}
exports.executionQuality = executionQuality;
async function launchState(baseUrl, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/state`, adminKey);
}
exports.launchState = launchState;
async function setLaunchMode(baseUrl, mode, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/mode`, { mode }, adminKey);
}
exports.setLaunchMode = setLaunchMode;
async function enableNextFamily(baseUrl, family, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/enable-next`, family ? { family } : {}, adminKey);
}
exports.enableNextFamily = enableNextFamily;
async function pauseLaunchFamily(baseUrl, family, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/pause-family`, { family }, adminKey);
}
exports.pauseLaunchFamily = pauseLaunchFamily;
async function revertLaunchFamily(baseUrl, family, adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/revert-family`, { family }, adminKey);
}
exports.revertLaunchFamily = revertLaunchFamily;
async function quarantineLaunchFamily(baseUrl, family, reasonCode = 'operator_quarantine', adminKey) {
    return await jpost(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/quarantine-family`, { family, reason_code: reasonCode }, adminKey);
}
exports.quarantineLaunchFamily = quarantineLaunchFamily;
async function launchFamilyDetail(baseUrl, family, adminKey) {
    return await jget(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/launch/family/${encodeURIComponent(family)}`, adminKey);
}
exports.launchFamilyDetail = launchFamilyDetail;
