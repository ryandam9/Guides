# Config-Driven Multi-Step Login Probe (Playwright)

> **Scope:** A small, throwaway Playwright script that walks a **multi-page login
> flow** (username page → email page → password/OTP page → submit → landing view)
> entirely from a **YAML config**. Built to discover and prototype the selectors
> for a portal whose login differs page-to-page, before wiring anything into a
> larger automation.

Folder: [`scripts/login-probe/`](../scripts/login-probe/) —
[`run-login-flow.js`](../scripts/login-probe/run-login-flow.js) ·
[`login-flow.example.yaml`](../scripts/login-probe/login-flow.example.yaml) ·
[`package.json`](../scripts/login-probe/package.json)

---

## 1. What it does

Some portals don't have a single login form — they walk you through several
pages, each with one field, sometimes inside an `<iframe>` or rendered
dynamically. This probe drives that flow from a config file so that adding,
reordering, or re-selecting a field is a **config edit, never a code change**.

For each step it:

1. **Searches every frame** (main document + nested iframes) and **polls until
   the control appears** — so late-rendered and iframed forms both work.
2. Optionally **types a value**, then does an **action** (`enter` / `click` /
   `none`).
3. Moves to the next step, which waits for *its* control — that's how the
   page-to-page transitions are handled.

At the end it waits for a **success signal** (text that only appears once you've
reached the landing/account view).

If a selector isn't found, it **dumps every candidate field and button on the
current page** (with a suggested selector for each) to the console and a JSON
file, plus a screenshot — so you can read off the real id/type and fix that one
line.

## 2. Install (standalone)

The script depends only on **`playwright`** and **`js-yaml`**. Install them once
inside the `scripts/login-probe/` folder — the bundled `package.json` pins both:

```bash
cd scripts/login-probe
npm install                      # installs playwright + js-yaml (from package.json)
npx playwright install chromium  # one-time browser download
```

No parent project and nothing else is required — `node_modules/` lives right in
that folder (and is git-ignored). If you ever see
`✗ Missing dependency "js-yaml"`, you're running it from a folder without those
deps installed; run the two commands above.

## 3. Config format

```yaml
startUrl: "Jaffa-url"
successText: "accounts view"     # body text that only appears once logged in
stepTimeoutMs: 20000             # how long to wait for each step's control

steps:
  - name: username
    selector: "id:username"      # selector forms below
    value: "your.username"       # literal value, right here in the file
  - name: password
    selector: "type:password"
    value: "your-password"
    secret: true                 # never echoed in the run log
    keys: ["Tab", "Enter"]       # submit by keyboard — see "Submitting" below
```

### Submitting a page

Each step, after any `value`, does **one** of:

| Field | Does | Use for |
| --- | --- | --- |
| `action: enter` | press Enter on the located element | single-field pages (email, OTP) |
| `action: click` | click the located element | a real submit button you can select |
| `action: none` | nothing (default when a value was typed) | just fill this field, submit later |
| `keys: ["Tab","Enter"]` | from the filled field, press the keys in order | **submit with no submit element** — Tab onto the submit control, then Enter |

`keys` replaces `action`. Focus starts on the field you just filled, so
`["Tab", "Enter"]` tabs to the submit button and activates it — no selector for
the button required. Add more `"Tab"`s if it's several tab-stops away, and tune
the pace with `keyDelayMs` (default 150).

### Keyboard-only pages (no selector at all)

Some pages are easiest to drive purely by keyboard — Tab onto the field, type,
Tab to the button, Enter. Omit `selector` entirely and the step becomes
**keyboard-only**: it types the value into whatever is currently focused and
presses these key lists via the keyboard.

| Field | Does |
| --- | --- |
| `preKeys: ["Tab"]` | keys pressed **before** typing — e.g. Tab off the URL bar onto the text box |
| `value: "…"` | typed into the **currently focused** element (not a located one) |
| `keys: ["Tab","Tab","Enter"]` | keys pressed **after** typing — Tab to the submit, then Enter |

#### Timing knobs

Every step (keyboard-only *or* selector) runs in this order, and each pause is
an optional millisecond value you can set independently — so you can wait both
**before and after entering the details**:

```
waitBeforeMs → [preKeys] → waitBeforeTypeMs → TYPE value → waitAfterTypeMs → [keys/action] → waitMs
```

| Field | Pause |
| --- | --- |
| `waitBeforeMs` | before the step does anything (e.g. let a new page load) |
| `waitBeforeTypeMs` | right **before** typing the value |
| `waitAfterTypeMs` | right **after** typing the value, before the keys/submit |
| `waitMs` | after the whole step (default `800`; set `0` to skip) |

```yaml
# Page 2: Tab into the box, type email, Tab twice, Enter, wait 5s — no selector.
- name: email
  waitBeforeMs: 2000
  preKeys: ["Tab"]
  value: "you@example.com"
  keys: ["Tab", "Tab", "Enter"]
  waitMs: 5000
```

`preKeys` also works on a selector step (it focuses the located element, then
presses them). Since a keyboard-only step doesn't locate anything, give it a
`waitBeforeMs` so a freshly-loaded page has time to render before it starts
tabbing. If the cursor doesn't land where you expect, adjust the `preKeys` count.

### Selector forms

| Form | Resolves to | Use when |
| --- | --- | --- |
| `id:usernameBox` | `[id="usernameBox"]` | a stable id exists (preferred) |
| `type:email` | `input[type="email"]` | no id — match by tag + type |
| `name:email` | `[name="email"]` | the field has a `name` |
| `testid:accSubmit` | `[data-testid="accSubmit"]` | the app exposes test ids |
| `text:Log in` | control whose visible text is "Log in" | buttons/links by label |
| `css:div.title` | raw CSS, used as-is | anything else |

### Values

Put the literal value in the file (`value: "your.username"`). Add
`secret: true` so passwords aren't echoed in the run log.

> **The config holds plaintext passwords — keep it private:** `chmod 600
> login-flow.yaml`. The script warns at startup if the file is readable by
> group/others.

## 4. MFA / OTP

You complete the OTP **in the browser**; the script just **waits** for the page
that appears afterward — no terminal input:

```yaml
- name: mfa-wait
  waitFor: "type:submit"     # a control that only appears AFTER the OTP page
  timeoutMs: 180000          # generous — time to fetch and type the code
```

When the run reaches it, it prints `⏳ enter the OTP/MFA in the BROWSER —
waiting…`, polls every frame for that selector/text, and continues the instant
it's visible. `waitFor` accepts the same selector forms as everything else.

If you'd rather it hold for an explicit keypress instead, use a `pause` step:

```yaml
- name: mfa
  pause: true
  message: "Approve the MFA push, then press Enter here"
  # expect: "text on the next page"   # optional: auto-continue when it appears
```

## 5. Ad-Hoc connection (optional)

Add an `adhoc:` block and, once the login steps reach the Account view, the
script continues into the vault's **Ad-Hoc connection** flow — the minimal
logic (open button → form → fill → Connect) ported from `sendcmd`
(`findClickable` / `fillField` / `setDropdown`), copied verbatim so it behaves
the same. **`sendcmd` itself is not modified** — this is an independent copy.

```yaml
adhoc:
  button:
    testIds: ["accPAdHocConnectionBtn"]   # data-testid tried first
    text: "ad[-\\s]?hoc\\s*connect"        # else match by name/text (regex)
  formProbe: 'input[formcontrolname="inpAddress" i]'   # frame that hosts the form
  formWait:  'input[formcontrolname="inpAddress" i]'
  fields:
    - { kind: dropdown, label: Platform, fc: ddlPolicy,               value: "PSM-SecureConnect" }
    - { kind: dropdown, label: Client,   fc: ddlConnectionComponents, value: "SSH" }
    - { kind: input, label: Address,  selector: 'input[formcontrolname="inpAddress" i]',  value: "10.0.0.10" }
    - { kind: input, label: Username, selector: 'input[formcontrolname="inpUsername" i]', value: "CORP\\you" }
    - { kind: input, label: Password, selector: 'input[formcontrolname="inpPassword" i]', value: "…", optional: true, secret: true }
  connect:
    text: "^\\s*connect\\s*$"
    primarySelector: "button.ui-button-primary"
```

It runs four steps, logging each: **1** click the Ad-Hoc button (by test-id or
name, across all frames; falls back to clicking the `accountsNavText` nav first),
**2** wait for the form frame to open, **3** fill inputs and dropdowns from
`fields`, **4** wait for **Connect** to become enabled, click it, and capture
the **session tab** that opens (its screenshot is saved to
`login-probe-session.png`). A missing button/field dumps the page's candidates,
same as the login steps. Remove the `adhoc:` block to stop at login.

> This connects (opens the remote session tab). Driving the session *inside*
> that tab — the Guacamole canvas, host-key, password, `kinit` — is a much
> larger surface that lives in `sendcmd`; it is out of scope for this probe.

## 6. Running it

From inside `scripts/login-probe/` (copy the example to your own config first):

```bash
cp login-flow.example.yaml login-flow.yaml   # then edit selectors + values
chmod 600 login-flow.yaml                     # holds plaintext creds
node run-login-flow.js login-flow.yaml

# just dump the first page's fields/buttons (no flow):
node run-login-flow.js login-flow.yaml --probe
```

The browser is left open at the end so you can inspect the result; press
`Ctrl+C` to close it. Screenshots and candidate-field JSON dumps are written to
the current directory (override with `PROBE_OUT=/some/dir`).

## 7. Notes

- **Iframes / dynamic forms:** handled — every step searches all frames and
  polls up to its timeout, the same way robust portal automations do.
- **This is a probe, not a product.** Once the selectors are dialed in, the
  natural next step is to translate the step list into whatever automation
  consumes it (the config is deliberately close to a declarative
  `login.steps[]` layout).
