'use strict';

// ── Ad-hoc CONFIG-DRIVEN multi-step login probe (throwaway — NOT the repo) ────
// Walks a multi-PAGE login (sketch: page1 username+password+"Log in" → page2
// email+Enter → page3 password+Enter → page4 Submit → wait for the Account view)
// entirely from a YAML config. Each step names ONE control by a selector, an
// optional value to type, and an action (enter | click | none). Steps run in
// order; the runner WAITS for each step's control to appear (up to a timeout),
// so page transitions and dynamically-generated forms are handled automatically.
//
// It searches EVERY frame (main doc + nested iframes), because a portal often
// renders the login form inside an <iframe>.
//
// This is a STANDALONE script — its only dependencies are `playwright` and
// `js-yaml`. Install them once in this folder:
//   npm install                 # if you have the package.json next to this file
//   # …or explicitly:
//   npm install js-yaml playwright && npx playwright install chromium
//
// Usage:
//   node run-login-flow.js login-flow.yaml
//   node run-login-flow.js login-flow.yaml --probe   # just dump the first page
//
// Secrets: put values straight in the config file (chmod 600 it), or pull them at
// runtime — "keychain:ITEM" reads from the macOS Keychain, "env:VAR" from an env
// var, "prompt:Msg" asks at the terminal. Mark a step `secret: true` so its value
// is never echoed in the run log.

const path = require('path');
const fs = require('fs');
const readline = require('readline');
const { execFileSync } = require('child_process');

// Lazy terminal prompt — for `pause` steps (finish MFA by hand, then Enter) and
// `prompt:` values (type an OTP at runtime so it's never in the config/env).
let _rl = null;
const rl = () => (_rl = _rl || readline.createInterface({ input: process.stdin, output: process.stdout }));
const ask = (q) => new Promise((res) => rl().question(q, (a) => res(a)));

// ── Dependencies — resolved from THIS folder's node_modules ───────────────────
// Node resolves a bare require() from node_modules walking up from this file, so
// `npm install` in this directory (or any parent) is all that's needed.
function need(mod) {
  try { return require(mod); }
  catch {
    console.error(`\n✗ Missing dependency "${mod}". Install the two deps in this folder, then re-run:\n` +
      `    npm install js-yaml playwright\n` +
      `    npx playwright install chromium\n`);
    process.exit(2);
  }
}
const { chromium } = need('playwright');
const yaml = need('js-yaml');

const cfgPath = process.argv[2];
const PROBE_ONLY = process.argv.includes('--probe');
if (!cfgPath) {
  console.error('Usage: node run-login-flow.js <config.yaml> [--probe]');
  process.exit(2);
}
const cfg = yaml.load(fs.readFileSync(cfgPath, 'utf8')) || {};

// The config holds plaintext credentials now — warn if others can read it.
try {
  const mode = fs.statSync(cfgPath).mode & 0o777;
  if (mode & 0o077) console.warn(`[warn] ${cfgPath} is accessible by group/others (mode ${mode.toString(8)}) but holds plaintext passwords. Run: chmod 600 ${cfgPath}`);
} catch { /* best-effort */ }
const OUT_DIR = process.env.PROBE_OUT || process.cwd();
const STEP_TIMEOUT = cfg.stepTimeoutMs || 20000;

// ── Selector spec → a per-frame locator factory ──────────────────────────────
// Forms: id:X · type:X (input[type=X]) · name:X · testid:X · text:X · css:<raw>.
// A bare string with no prefix is treated as raw CSS.
function locatorFactory(spec) {
  const s = String(spec);
  const i = s.indexOf(':');
  const kind = i > 0 ? s.slice(0, i) : 'css';
  const val = i > 0 ? s.slice(i + 1) : s;
  switch (kind) {
    case 'id': return (f) => f.locator(`[id="${val}"]`);
    case 'type': return (f) => f.locator(`input[type="${val}"]`);
    case 'name': return (f) => f.locator(`[name="${val}"]`);
    case 'testid': return (f) => f.locator(`[data-testid="${val}"]`);
    case 'text': return (f) => f.getByText(val, { exact: false });
    case 'css': default: return (f) => f.locator(val);
  }
}

// Poll EVERY frame until the spec resolves to a visible element (dynamic render
// + iframes), mirroring sendcmd's findClickable/fillField. Returns the locator
// (already .first()) or null on timeout.
async function findInAnyFrame(page, spec, { timeout = STEP_TIMEOUT } = {}) {
  const make = locatorFactory(spec);
  const deadline = Date.now() + timeout;
  let announced = false;
  do {
    for (const frame of page.frames()) {
      let el;
      try { el = make(frame).first(); } catch { continue; } // frame detached
      if (await el.isVisible().catch(() => false)) return el;
    }
    if (!announced) { console.log(`      · waiting for ${spec} (all frames)…`); announced = true; }
    await page.waitForTimeout(250);
  } while (Date.now() < deadline);
  return null;
}

// Read a secret from the macOS Keychain via the `security` CLI. The item is
// matched by service name (-s — how `security add-generic-password -s NAME …`
// stores it, and how Keychain Access labels it), falling back to account (-a)
// then label (-l). Returns the stored string, or null if not found.
function readKeychain(item) {
  if (process.platform !== 'darwin') {
    console.error(`   ✗ keychain: values require macOS (the \`security\` CLI); this host is "${process.platform}". Use env:/prompt: instead, or run on your Mac.`);
    process.exit(3);
  }
  for (const flag of ['-s', '-a', '-l']) {
    try {
      const out = execFileSync('security', ['find-generic-password', flag, item, '-w'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
      const val = out.replace(/\r?\n$/, '');   // -w appends a trailing newline
      if (val) return val;
    } catch { /* not found with this matcher — try the next */ }
  }
  return null;
}

async function resolveValue(step) {
  const v = step.value;
  if (v == null) return null;
  const s = String(v);
  if (s.startsWith('env:')) {
    const name = s.slice(4);
    const got = process.env[name];
    if (got == null || got === '') {
      console.error(`   ✗ step "${step.name}": env var ${name} is unset. Run: export ${name}='…'`);
      process.exit(3);
    }
    return got;
  }
  // keychain:ITEM — read from the macOS Keychain at runtime (never stored in the
  // config or env). Add it once: security add-generic-password -a "$USER" -s ITEM -w
  if (s.startsWith('keychain:')) {
    const item = s.slice('keychain:'.length);
    const got = readKeychain(item);
    if (got == null || got === '') {
      console.error(`   ✗ step "${step.name}": keychain item "${item}" not found (or empty). Add it, e.g.:  security add-generic-password -a "$USER" -s ${item} -w`);
      process.exit(3);
    }
    return got;
  }
  // prompt:Message — read the value from the terminal at runtime (OTP / MFA
  // code). Kept out of the config and env by design.
  if (s.startsWith('prompt:')) {
    const msg = s.slice('prompt:'.length) || `Enter value for "${step.name}"`;
    return (await ask(`   ⌨  ${msg}: `)).trim();
  }
  return s;
}

// Dump the candidate inputs/buttons across all frames — shown when a step's
// selector misses, so you can read off the real id/type and fix the config.
async function dumpCandidates(page, tag) {
  const collect = () => {
    const vis = (el) => {
      const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
    };
    const at = (el, n) => el.getAttribute(n) || '';
    const inputs = [...document.querySelectorAll('input,textarea,select')]
      .filter((e) => e.type !== 'hidden' && vis(e))
      .map((e) => ({ tag: e.tagName.toLowerCase(), type: e.type || '', id: at(e, 'id'), name: at(e, 'name'), fc: at(e, 'formcontrolname'), testid: at(e, 'data-testid'), ph: at(e, 'placeholder') }));
    const buttons = [...document.querySelectorAll('button,a,[role="button"],input[type="submit"],input[type="button"],div.title')]
      .filter(vis)
      .map((e) => ({ tag: e.tagName.toLowerCase(), text: (e.innerText || e.value || '').trim().slice(0, 60), id: at(e, 'id'), testid: at(e, 'data-testid') }))
      .filter((b) => b.text || b.id || b.testid);
    return { url: location.href, title: document.title, inputs, buttons };
  };
  console.log(`\n══ candidates on ${tag} ══════════════════════════════`);
  for (const frame of page.frames()) {
    const d = await frame.evaluate(collect).catch(() => null);
    if (!d || (!d.inputs.length && !d.buttons.length)) continue;
    const where = frame === page.mainFrame() ? 'main document' : `iframe ${frame.url()}`;
    console.log(`  ── ${where}  (${d.url})`);
    for (const i of d.inputs) {
      const best = i.id ? `id:${i.id}` : i.name ? `name:${i.name}` : i.fc ? `css:[formcontrolname="${i.fc}"]` : `type:${i.type}`;
      console.log(`     input type=${i.type} ${i.ph ? `ph=${JSON.stringify(i.ph)} ` : ''}→ selector: "${best}"`);
    }
    for (const b of d.buttons) {
      const best = b.testid ? `testid:${b.testid}` : b.id ? `id:${b.id}` : `text:${b.text}`;
      console.log(`     ${b.tag} text=${JSON.stringify(b.text)} → selector: "${best}"`);
    }
  }
  const file = path.join(OUT_DIR, `login-probe-${tag.replace(/\W+/g, '_')}.json`);
  const record = [];
  for (const frame of page.frames()) {
    const d = await frame.evaluate(collect).catch(() => null);
    if (d) record.push({ frame: frame === page.mainFrame() ? 'main' : frame.url(), ...d });
  }
  fs.writeFileSync(file, JSON.stringify(record, null, 2));
  console.log(`   📄 ${file}`);
}

// Wait until some frame's visible body text contains the success phrase.
async function waitForSuccess(page, phrase, timeout = 30000) {
  const re = new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
  const deadline = Date.now() + timeout;
  do {
    for (const frame of page.frames()) {
      const txt = await frame.evaluate(() => document.body ? document.body.innerText : '').catch(() => '');
      if (re.test(txt)) return true;
    }
    await page.waitForTimeout(400);
  } while (Date.now() < deadline);
  return false;
}

// ═══════════════════════════════════════════════════════════════════════════
// Ad-Hoc connection — MINIMAL logic ported from sendcmd (automate.js / forms.js)
// to open the Ad-Hoc form, fill it, and click Connect. Kept faithful to the
// originals (findClickable / fillField / setDropdown) so it behaves the same;
// sendcmd itself is NOT modified — this is an independent copy.
// ═══════════════════════════════════════════════════════════════════════════

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const escapeRegex = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Positional field support — an extra control that has no id/name/label is
// located purely by its POSITION among the form's same-kind controls (1-based),
// matching the numbering printed by the form-controls discovery dump below.
const POS_INPUT_SEL = 'input:not([type="hidden"]):visible, textarea:visible';
const POS_DROPDOWN_SEL = 'select:visible, p-dropdown:visible, mat-select:visible, [role="combobox"]:visible, .ui-dropdown:visible, .p-dropdown:visible';

// fillInputAt — fill the Nth (1-based) visible input/textarea on the form, for a
// field that can only be identified by position. Same fill→click+type fallback
// as a selector step, polling until the control renders.
async function fillInputAt(scope, index1, value, { timeout = 15000 } = {}) {
  const el = scope.locator(POS_INPUT_SEL).nth(index1 - 1);
  const deadline = Date.now() + timeout;
  do {
    if (await el.count().catch(() => 0)) {
      try { await el.fill(value, { timeout: 1000 }); return true; }
      catch { try { await el.click({ timeout: 1000 }); await el.type(value); return true; } catch { /* retry */ } }
    }
    await sleep(250);
  } while (Date.now() < deadline);
  throw new Error(`no fillable input at position ${index1} on the form`);
}

// findClickable — search EVERY frame for a control by data-testid, accessible
// name, or visible text; poll until it appears. (sendcmd automate.js:1776)
function clickableCandidates(root, nameRegex, testIds) {
  return [
    ...testIds.map((id) => root.locator(`[data-testid="${id}"]`)),
    root.getByRole('button', { name: nameRegex }),
    root.getByRole('link', { name: nameRegex }),
    root.locator('button, a, [role="button"], [role="link"]').filter({ hasText: nameRegex }),
    root.getByText(nameRegex),
  ];
}
async function findClickable(page, nameRegex, { timeout = 30000, testIds = [] } = {}) {
  const deadline = Date.now() + timeout;
  do {
    for (const frame of page.frames()) {
      let candidates;
      try { candidates = clickableCandidates(frame, nameRegex, testIds); } catch { continue; }
      for (const locator of candidates) {
        const el = locator.first();
        if (await el.isVisible().catch(() => false)) return el;
      }
    }
    await sleep(250);
  } while (Date.now() < deadline);
  return null;
}

// fillField — fill by selector → label → placeholder → name/id, polling until
// the field renders (splash/interstitial pages). (sendcmd automate.js:1732)
async function fillField(scope, labelText, value, { optional = false, timeout, selector } = {}) {
  const limit = timeout ?? (optional ? 3000 : 30000);
  const candidates = [
    ...(selector ? [scope.locator(selector)] : []),
    scope.getByLabel(labelText, { exact: false }),
    scope.getByPlaceholder(labelText, { exact: false }),
    scope.locator(`input[name="${labelText}" i], input[id="${labelText}" i]`),
  ];
  const deadline = Date.now() + limit;
  do {
    for (const locator of candidates) {
      const el = locator.first();
      if (await el.count().catch(() => 0)) {
        try { await el.fill(value, { timeout: 1000 }); return true; } catch { /* next */ }
      }
    }
    await sleep(250);
  } while (Date.now() < deadline);
  if (!optional) throw new Error(`Could not locate the "${labelText}" field within ${limit}ms.`);
  return false;
}

// setDropdown — native <select>, PrimeNG <p-dropdown> overlay, or a label-based
// combobox. Matched by formcontrolname `fc`, a raw `selector`, or a pre-resolved
// `trigger` locator (for an extra field found only by position). (ported from
// sendcmd automate.js:1822)
async function setDropdown(scope, page, field, value, { timeout = 15000 } = {}) {
  const { fc, label, selector, trigger: preTrigger } = field;
  const wanted = new RegExp(escapeRegex(value), 'i');
  const wantedExact = new RegExp(`^\\s*${escapeRegex(value)}\\s*$`, 'i');

  // Native <select>: a positional trigger or a `selector` may point straight at
  // one; otherwise build it from fc.
  const nativeSel = (preTrigger || (selector ? scope.locator(selector) : scope.locator(`select[formcontrolname="${fc}" i]`))).first();
  if (await nativeSel.count().catch(() => 0)) {
    try { await nativeSel.selectOption({ label: value }); return true; } catch { /* not a native select / fall through */ }
  }

  // Custom dropdown trigger: the positional element, the given selector, else the
  // fc-based p-dropdown.
  let trigger;
  if (preTrigger) {
    trigger = preTrigger;
  } else if (selector) {
    trigger = scope.locator(selector).first();
  } else {
    const prime = scope.locator(`p-dropdown[formcontrolname="${fc}" i]`).first();
    trigger = (await prime.count().catch(() => 0)) ? prime : scope.locator(`[formcontrolname="${fc}" i]`).first();
  }
  if (await trigger.count().catch(() => 0)) {
    const shown = (await trigger.innerText().catch(() => '')) || '';
    if (wantedExact.test(shown)) { console.log(`      ${label} already set to "${value}".`); return true; }
    await trigger.click().catch(() => {});

    const filter = scope.locator('.ui-dropdown-filter input, .p-dropdown-filter, input.ui-dropdown-filter').first();
    if (await filter.isVisible().catch(() => false)) await filter.fill(value).catch(() => {});

    const optSel = '.ui-dropdown-item, .p-dropdown-item, p-dropdownitem, li[role="option"], [role="option"]';
    const deadline = Date.now() + timeout;
    do {
      let opt = scope.locator(optSel).filter({ hasText: wantedExact }).first();
      if (!(await opt.isVisible().catch(() => false))) opt = scope.locator(optSel).filter({ hasText: wanted }).first();
      if (await opt.isVisible().catch(() => false)) { await opt.click(); return true; }
      await sleep(200);
    } while (Date.now() < deadline);
    console.warn(`   [warn] Option "${value}" not found in the ${label} dropdown.`);
    await page.keyboard.press('Escape').catch(() => {});
  }

  const combo = scope.getByLabel(label, { exact: false }).first();
  if (await combo.count().catch(() => 0)) {
    try {
      await combo.click();
      const option = scope.getByRole('option', { name: value }).first();
      if (await option.count().catch(() => 0)) { await option.click(); return true; }
      await combo.fill(value).catch(() => {});
      return true;
    } catch { /* ignore */ }
  }
  console.warn(`   [warn] Could not set "${label}" to "${value}" — leaving default.`);
  return false;
}

// List every input + dropdown on the opened form, with a ready-to-paste config
// line for each — so an extra field you didn't know about is easy to add to
// `adhoc.fields`. Prints to the console and saves a JSON dump.
async function dumpFormControls(formFrame, tag) {
  const collect = () => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const at = (el, n) => el.getAttribute(n) || '';
    const labelOf = (el) => {
      if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l && l.textContent.trim()) return l.textContent.trim(); }
      const w = el.closest('label'); if (w && w.textContent.trim()) return w.textContent.trim();
      return at(el, 'aria-label') || at(el, 'placeholder') || '';
    };
    const inputs = [...document.querySelectorAll('input, textarea')].filter((e) => e.type !== 'hidden' && vis(e))
      .map((e) => ({ control: 'input', type: e.type || 'text', fc: at(e, 'formcontrolname'), id: at(e, 'id'), name: at(e, 'name'), label: labelOf(e) }));
    const dds = [...document.querySelectorAll('select, p-dropdown, mat-select, [role="combobox"], .ui-dropdown, .p-dropdown')].filter(vis)
      .map((e) => ({ control: 'dropdown', tag: e.tagName.toLowerCase(), fc: at(e, 'formcontrolname'), id: at(e, 'id'), name: at(e, 'name'), label: labelOf(e), shown: (e.innerText || '').trim().slice(0, 40) }));
    return { url: location.href, inputs, dds };
  };
  const d = await formFrame.evaluate(collect).catch(() => null);
  if (!d) return;
  console.log('   ── form controls (add any missing one to adhoc.fields) ──');
  // `pos` is the control's 1-based position among its own kind — use it for a
  // field with no id/name/label (`position:`), filled by slot instead of selector.
  const inputLine = (c, pos) => c.fc ? `{ kind: input, label: ${c.label || c.fc}, selector: 'input[formcontrolname="${c.fc}" i]', value: "" }`
    : c.id ? `{ kind: input, label: ${c.label || c.id}, selector: '#${c.id}', value: "" }`
    : c.name ? `{ kind: input, label: ${c.label || c.name}, selector: '[name="${c.name}"]', value: "" }`
    : `{ kind: input, position: ${pos}, value: "" }   # no id/name/label — filled by position`;
  const ddLine = (c, pos) => c.fc ? `{ kind: dropdown, label: ${c.label || c.fc}, fc: ${c.fc}, value: "" }`
    : c.id ? `{ kind: dropdown, label: ${c.label || c.id}, selector: '#${c.id}', value: "" }`
    : `{ kind: dropdown, position: ${pos}, value: "" }   # no id — filled by position`;
  d.inputs.forEach((c, i) => console.log(`     input  #${i + 1}  type=${c.type}  ${c.label ? `“${c.label}”  ` : ''}→  ${inputLine(c, i + 1)}`));
  d.dds.forEach((c, i) => console.log(`     dropdown #${i + 1}  ${c.shown ? `[${c.shown}]  ` : ''}${c.label ? `“${c.label}”  ` : ''}→  ${ddLine(c, i + 1)}`));
  const file = path.join(OUT_DIR, `login-probe-${tag}.json`);
  fs.writeFileSync(file, JSON.stringify(d, null, 2));
  console.log(`   📄 ${file}`);
}

// Optional keyboard steps that run AFTER Connect — e.g. dismiss a host-key or
// connection dialog on the session tab. Each entry: { verify (selector — press
// only once this is visible), verifyTimeoutMs, waitMs (default 5000, or 0 when
// verify is set), keys (["Enter"] / ["Tab","Enter"] or a "Tab Enter" string),
// keyDelayMs }. An absent/empty list runs nothing, so each step is opt-in.
async function runPostConnect(targetPage, steps) {
  if (!Array.isArray(steps) || !steps.length) return;
  console.log('▶ 5. post-Connect keyboard steps…');
  for (const [i, st] of steps.entries()) {
    // verify: act only once the tab is actually SHOWING the expected content,
    // instead of a blind timed wait. Never seen → SKIP this step's keys —
    // pressing keys on the wrong screen is worse than doing nothing. (Canvas
    // terminals render no DOM text, so those still need a waitMs instead.)
    if (st.verify) {
      const to = st.verifyTimeoutMs || 15000;
      console.log(`   🔎 step ${i + 1}: waiting for ${JSON.stringify(st.verify)} (up to ${Math.round(to / 1000)}s)…`);
      const seen = await findInAnyFrame(targetPage, st.verify, { timeout: to });
      if (!seen) { console.warn(`   [warn] step ${i + 1}: ${JSON.stringify(st.verify)} never appeared — skipping its keys`); continue; }
      console.log('   ✓ verified');
    }
    const wait = st.waitMs != null ? st.waitMs : (st.verify ? 0 : 5000);
    if (wait) { console.log(`   ⏱ step ${i + 1}: waiting ${wait}ms…`); await targetPage.waitForTimeout(wait); }
    const keys = Array.isArray(st.keys) ? st.keys : String(st.keys || '').split(/[\s,]+/).filter(Boolean);
    for (const k of keys) {
      await targetPage.keyboard.press(k).catch((e) => console.warn(`   [warn] press ${k}: ${e.message}`));
      console.log(`   ⌨ ${k}`);
      await targetPage.waitForTimeout(st.keyDelayMs || 150);
    }
    console.log(`   ✓ post-Connect step ${i + 1}: [${keys.join(', ')}]`);
  }
}

// The Ad-Hoc connect flow: open the form, fill it, click Connect, capture the
// session tab. `ad` is the config's `adhoc:` block. Returns the new session
// Page on success, or false.
async function runAdhoc(page, context, ad) {
  console.log('\n═══ Ad-Hoc connection ═══');

  // 1. Open the Ad-Hoc form (button by test-id / name, across all frames).
  const testIds = (ad.button && ad.button.testIds) || [];
  const nameRe = new RegExp((ad.button && ad.button.text) || 'ad[-\\s]?hoc\\s*connect', 'i');
  console.log('▶ 1. clicking the Ad-Hoc connection button…');
  let btn = await findClickable(page, nameRe, { timeout: 12000, testIds });
  if (!btn && ad.accountsNavText) {
    const nav = await findClickable(page, new RegExp(ad.accountsNavText, 'i'), { timeout: 5000 });
    if (nav) { console.log('   · clicking the Accounts nav first…'); await nav.click().catch(() => {}); btn = await findClickable(page, nameRe, { timeout: 20000, testIds }); }
  }
  if (!btn) { console.error('   ✗ Ad-Hoc button not found'); await dumpCandidates(page, 'adhoc-button-miss'); return false; }
  await btn.click();

  // 2. Find the frame that hosts the form, then wait for it to be visible.
  console.log('▶ 2. waiting for the form to open…');
  let formFrame = page;
  const fd = Date.now() + 15000;
  for (;;) {
    let found = null;
    for (const f of page.frames()) { if (await f.locator(ad.formProbe).first().count().catch(() => 0)) { found = f; break; } }
    if (found) { formFrame = found; break; }
    if (Date.now() >= fd) break;
    await sleep(250);
  }
  await formFrame.locator(ad.formWait).first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  console.log('   ✓ form open');

  // 2b. DISCOVERY — list every control on the form so an extra field you don't
  // yet know about is revealed with a ready-to-paste config line. On by default;
  // set `adhoc.probeForm: false` to silence it once your config is complete.
  if (ad.probeForm !== false) await dumpFormControls(formFrame, 'adhoc-form');

  // 3. Fill the form (input fields + dropdowns), from the config. Each field is
  // isolated so one unknown/misconfigured field can't abort the whole run.
  console.log('▶ 3. filling the form…');
  const filled = {};
  const posSeen = {};                 // per-kind counter → a field's implicit slot
  for (const f of ad.fields || []) {
    const kind = f.kind || 'input';
    posSeen[kind] = (posSeen[kind] || 0) + 1;
    // A field with no id/selector/fc/label (or an explicit `position:`) is filled
    // by POSITION. `adhoc.fields` is already in form order, so a positional
    // field's slot is just its ordinal among same-kind fields here.
    const byPosition = f.position != null || (!f.selector && !f.fc && !f.label);
    const position = f.position != null ? f.position : posSeen[kind];
    const label = f.label || `${kind}#${position}`;
    try {
      const value = await resolveValue({ value: f.value, secret: f.secret, name: label });
      if (f.skipIfEmpty && !value) { continue; }
      if (kind === 'dropdown') {
        const spec = byPosition
          ? { trigger: formFrame.locator(POS_DROPDOWN_SEL).nth(position - 1), label }
          : { fc: f.fc, selector: f.selector, label };
        filled[label] = await setDropdown(formFrame, page, spec, value);
      } else if (byPosition) {
        filled[label] = await fillInputAt(formFrame, position, value);
      } else {
        filled[label] = await fillField(formFrame, label, value, { optional: !!f.optional, ...(f.selector ? { selector: f.selector } : {}) });
      }
      console.log(`   ✓ ${kind}${byPosition ? ` @pos ${position}` : ''} ${label}: ${f.secret ? '(secret hidden)' : JSON.stringify(value)}`);
    } catch (e) {
      filled[label] = false;
      console.warn(`   [warn] ${label}: ${e.message}`);
    }
  }

  // 4. Click Connect (wait for it to become enabled first), capture the tab.
  console.log('▶ 4. submitting (Connect)…');
  const connectRe = new RegExp((ad.connect && ad.connect.text) || '^\\s*connect\\s*$', 'i');
  const primary = formFrame.locator((ad.connect && ad.connect.primarySelector) || 'button.ui-button-primary').filter({ hasText: connectRe }).first();
  const byRole = formFrame.getByRole('button', { name: connectRe }).first();
  const connect = (await primary.count().catch(() => 0)) ? primary : byRole;

  let saw = false, enabled = false;
  const cd = Date.now() + 20000;
  do {
    if (await connect.count().catch(() => 0)) { saw = true; if (await connect.isEnabled().catch(() => false)) { enabled = true; break; } }
    await sleep(300);
  } while (Date.now() < cd);
  if (!saw) { console.error('   ✗ Connect button not found'); await dumpCandidates(page, 'connect-miss'); return false; }
  if (!enabled) { console.error(`   ✗ Connect stayed disabled — the form is incomplete/invalid. Filled: ${JSON.stringify(filled)}`); return false; }

  console.log('   · clicking Connect, waiting for the session tab…');
  const [sessionPage] = await Promise.all([
    context.waitForEvent('page', { timeout: 60000 }).catch(() => null),
    connect.click(),
  ]);
  if (sessionPage) {
    await sessionPage.bringToFront().catch(() => {});
    await sessionPage.waitForLoadState('domcontentloaded').catch(() => {});
    console.log(`   ✅ connected — session tab opened: ${sessionPage.url() || '(loading)'}`);
  } else {
    console.warn('   ⚠ no new session tab opened after Connect');
  }

  // 5. Optional, config-driven keyboard steps after Connect. They run on the
  // session tab if one opened, else the main page. Absent → nothing happens.
  await runPostConnect(sessionPage || page, ad.postConnect);
  return sessionPage || false;
}

(async () => {
  const browser = await chromium.launch({ headless: false, args: ['--start-maximized'] });
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();

  console.log(`Opening ${cfg.startUrl} …`);
  await page.goto(cfg.startUrl, { waitUntil: 'domcontentloaded' }).catch((e) => console.warn('goto:', e.message));
  await page.waitForTimeout(1000);

  if (PROBE_ONLY) {
    await dumpCandidates(page, 'start');
    console.log('\n--probe: dumped the first page only. Remove --probe to run the full flow.');
    await page.waitForTimeout(1500);
    await browser.close();
    return;
  }

  let ok = true;
  for (const [n, step] of (cfg.steps || []).entries()) {
    const tag = `${n + 1}/${cfg.steps.length} ${step.name || step.selector || step.waitFor || 'pause'}`;
    console.log(`\n▶ step ${tag}`);

    // verify: CONTENT CHECK before the step acts — wait until the page is
    // actually showing the named control/text (same selector grammar as
    // `selector`, searched across all frames). This replaces blind timed waits
    // on slow pages: the step proceeds the moment the content is visible, and
    // fails loudly (with a candidates dump + screenshot) if it never appears —
    // so keys are never typed into the wrong screen. Especially useful on
    // keyboard-only steps, which otherwise act on whatever happens to be there.
    if (step.verify) {
      const to = step.verifyTimeoutMs || step.timeoutMs || STEP_TIMEOUT;
      console.log(`   🔎 verifying the page shows ${JSON.stringify(step.verify)} (up to ${Math.round(to / 1000)}s)…`);
      const seen = await findInAnyFrame(page, step.verify, { timeout: to });
      if (!seen) {
        if (step.optional) { console.log('   • optional — expected content not seen, skipping step'); continue; }
        console.error(`   ✗ the page never showed ${JSON.stringify(step.verify)} — wrong page, or still loading after ${Math.round(to / 1000)}s`);
        await dumpCandidates(page, `verify-miss-${n + 1}`);
        await page.screenshot({ path: path.join(OUT_DIR, `login-probe-verify-miss-${n + 1}.png`), fullPage: true }).catch(() => {});
        ok = false; break;
      }
      console.log('   ✓ verified — page is showing the expected content');
    }

    // waitFor step — NO terminal input. You do the OTP/MFA in the BROWSER; the
    // runner just watches until the page that appears AFTER it shows up (its
    // selector/text becomes visible), then continues. Give it a long timeout so
    // there's time to fetch and type the code by hand.
    if (step.waitFor) {
      const to = step.timeoutMs || 180000;
      console.log(`   ⏳ enter the OTP/MFA in the BROWSER — waiting (up to ${Math.round(to / 1000)}s) for ${JSON.stringify(step.waitFor)} …`);
      const seen = await findInAnyFrame(page, step.waitFor, { timeout: to });
      if (seen) { console.log('   ✓ next page detected — continuing'); await page.waitForTimeout(step.waitMs || 300); continue; }
      if (step.optional) { console.log('   • optional wait — not seen, continuing'); continue; }
      console.error(`   ✗ ${JSON.stringify(step.waitFor)} never appeared`);
      await dumpCandidates(page, `waitfor-miss-${n + 1}`);
      ok = false; break;
    }

    // Pause step (or any step with pause: true) — hold for a manual action
    // (approve MFA in the browser, read an OTP off your phone), then continue
    // when you press Enter here. `expect:` optionally waits for the resulting
    // page instead of a keypress (whichever you prefer).
    if (step.action === 'pause' || step.pause) {
      const msg = step.message || 'Complete the MFA/OTP step in the browser';
      if (step.expect) {
        console.log(`   ⏸  ${msg} — waiting for ${JSON.stringify(step.expect)} to appear (or press Enter to force-continue)…`);
        const raced = await Promise.race([
          waitForSuccess(page, step.expect, step.timeoutMs || 120000).then((r) => (r ? 'found' : 'timeout')),
          ask('').then(() => 'enter'),
        ]);
        console.log(raced === 'found' ? '   ▶ detected — continuing' : '   ▶ continuing');
      } else {
        await ask(`   ⏸  ${msg}, then press Enter here to continue… `);
      }
      // A pause step may still name a field to fill AFTER the wait (e.g. type an
      // OTP once the OTP page is up); if it has no selector, it's a pure pause.
      if (!step.selector) { await page.waitForTimeout(step.waitMs || 300); continue; }
    }

    // Press a list of keys via the keyboard (space/comma string or array).
    const pressKeys = async (spec) => {
      const keys = Array.isArray(spec) ? spec : String(spec).split(/[\s,]+/).filter(Boolean);
      for (const k of keys) {
        await page.keyboard.press(k);
        console.log(`   ⌨ ${k}`);
        await page.waitForTimeout(step.keyDelayMs || 150);
      }
    };

    // A named fixed pause (logged so the run shows where time went).
    const pause = async (ms, label) => { if (ms) { console.log(`   ⏱ ${label} ${ms}ms…`); await page.waitForTimeout(ms); } };

    // Per-step timing knobs (all optional, milliseconds). `verify` (above) runs
    // before all of these — prefer it over a blind waitBeforeMs on slow pages.
    //   waitBeforeMs      — before the step does anything
    //   waitBeforeTypeMs  — after preKeys, right BEFORE typing the value
    //   waitAfterTypeMs   — right AFTER typing the value, before keys/submit
    //   waitMs            — after the whole step (default 800)
    await pause(step.waitBeforeMs, 'before step');

    const value = await resolveValue(step);

    if (step.selector) {
      // ── Selector step: locate the control, then fill / act on it ──────────
      const el = await findInAnyFrame(page, step.selector, { timeout: step.timeoutMs || STEP_TIMEOUT });
      if (!el) {
        if (step.optional) { console.log('   • optional — not found, skipping'); continue; }
        console.error(`   ✗ selector not found: ${step.selector}`);
        await dumpCandidates(page, `miss-step-${n + 1}`);
        await page.screenshot({ path: path.join(OUT_DIR, `login-probe-miss-${n + 1}.png`), fullPage: true }).catch(() => {});
        ok = false;
        break;
      }
      if (step.preKeys != null) { await el.focus().catch(() => {}); await pressKeys(step.preKeys); }
      if (value != null) {
        await pause(step.waitBeforeTypeMs, 'before typing');
        await el.fill(value, { timeout: 5000 }).catch(async () => { await el.click().catch(() => {}); await el.type(value); });
        console.log(`   ✓ filled ${step.secret ? '(secret hidden)' : JSON.stringify(value)}`);
        await pause(step.waitAfterTypeMs, 'after typing');
      }
      // keys: a key sequence from the just-filled field (e.g. [Tab, Enter]) to
      // reach + activate the submit control WITHOUT naming it. `keys` replaces
      // `action`; focus starts on the filled field (fill focuses it).
      if (step.keys != null) {
        if (value == null && step.preKeys == null) await el.focus().catch(() => {});
        await pressKeys(step.keys);
      } else {
        const action = step.action || (value != null ? 'none' : 'click');
        if (action === 'enter') { await el.press('Enter'); console.log('   ↵ pressed Enter'); }
        else if (action === 'click') { await el.click(); console.log('   ✓ clicked'); }
      }
    } else {
      // ── Keyboard-only step (no selector): operate on the CURRENT focus ─────
      // e.g. preKeys [Tab] to move off the URL bar into the text box, type the
      // value into whatever is focused, then keys [Tab, Tab, Enter] to submit.
      if (step.preKeys != null) await pressKeys(step.preKeys);
      if (value != null) {
        await pause(step.waitBeforeTypeMs, 'before typing');
        await page.keyboard.type(value, { delay: step.typeDelayMs || 30 });
        console.log(`   ⌨ typed ${step.secret ? '(secret hidden)' : JSON.stringify(value)}`);
        await pause(step.waitAfterTypeMs, 'after typing');
      }
      if (step.keys != null) await pressKeys(step.keys);
      else if (step.action === 'enter') { await page.keyboard.press('Enter'); console.log('   ↵ pressed Enter'); }
    }
    await pause(step.waitMs != null ? step.waitMs : 800, 'after step');
  }

  if (ok) {
    const phrase = cfg.successText || cfg.successSelector || 'accounts view';
    console.log(`\n⏳ waiting for the Account view (body contains ${JSON.stringify(phrase)})…`);
    const reached = await waitForSuccess(page, phrase, cfg.successTimeoutMs || 30000);
    console.log(reached ? '\n✅ Account view reached — login flow works.' : '\n⚠ Did not detect the Account view within the timeout.');
    if (!reached) await dumpCandidates(page, 'after-submit');
    await page.screenshot({ path: path.join(OUT_DIR, 'login-probe-final.png'), fullPage: true }).catch(() => {});
    console.log(`   📸 ${path.join(OUT_DIR, 'login-probe-final.png')}`);
  }

  // ── Ad-Hoc connection (if configured): open form → fill → Connect ─────────
  if (ok && cfg.adhoc) {
    const sessionPage = await runAdhoc(page, context, cfg.adhoc);
    await page.screenshot({ path: path.join(OUT_DIR, 'login-probe-adhoc.png'), fullPage: true }).catch(() => {});
    if (sessionPage) {
      await sessionPage.screenshot({ path: path.join(OUT_DIR, 'login-probe-session.png') }).catch(() => {});
      console.log(`   📸 session screenshot → ${path.join(OUT_DIR, 'login-probe-session.png')}`);
    }
  }

  console.log('\nBrowser left open — inspect, then press Ctrl+C to close.');
  await new Promise(() => {});
})().catch((e) => { console.error(e); process.exit(1); });
