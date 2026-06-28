# Crypto Payment Flow — Design Spec
**Date:** 2026-06-28  
**Status:** Approved  
**Scope:** Kiosk app (RPi) + kiosk-manager web app + Firestore

---

## Overview

Enables customers to pay with cryptocurrency at the GreenStar coffee kiosk. A static QR code image on the Square Terminal idle screen links to a web page where the customer selects their coin and initiates a session. The kiosk enters crypto mode, waits for a payment trigger (MDB vend, manual modal, or direct Bitcoin selection), then displays a payment QR on the Square Terminal. A countdown timer governs both phases; Firestore is the single source of truth for all state.

Bitcoin payment QR generation and processor integration are out of scope for this spec (next step). Placeholder links are used where the processor would be called.

---

## Architecture

```
Customer phone
    │  scan static QR image on Square Terminal idle screen
    ▼
kiosk-manager web app  (/enable-crypto/[kiosk_id])
    │  write crypto_session { status: "waiting_for_vend", coin }
    ▼
Firestore  (/kiosks/{kiosk_id}/crypto_sessions/active)
    │  on_snapshot listener
    ▼
Kiosk app (RPi) — enters crypto mode, shows live UI indicator
    │
    │  THEN one of three payment triggers:
    ├─ A) MDB sends vend signal with item price (while crypto mode active)
    ├─ B) Manual payment modal — operator enters amount, taps ₿ Bitcoin (crypto mode active)
    └─ C) Direct — operator selects Bitcoin in payment modal, no active web session
    │
    ▼
Kiosk has coin + amount
    │  write crypto_session { status: "payment_shown", amount_usd,
    │                         payment_link, amount_crypto, expires_at }
    ▼
Square Terminal — POST /v2/terminals/actions (QR_CODE with payment_link)
    │
    ▼
Firestore (web page reads in real time)
    ├─ shows payment QR + amounts + countdown
    ├─ "Need 1 more minute?" button (one-time use)
    └─ external processor writes "paid" → terminal QR cleared, web shows ✓
```

The web page and kiosk never communicate directly. Firestore is the only channel. The `expires_at` timestamp is the authoritative timer for both sides — neither side runs an independent clock.

---

## Firestore Schema

**Path:** `/kiosks/{kiosk_id}/crypto_sessions/active`

| Field | Type | Description |
|---|---|---|
| `session_id` | string | UUID — prevents stale sessions from re-triggering on reconnect |
| `status` | string | `"waiting_for_vend"` \| `"payment_shown"` \| `"paid"` \| `"expired"` |
| `coin` | string | `"BTC"` \| `"ETH"` \| `"SOL"` \| `"LTC"` (extensible) |
| `created_at` | timestamp | When the customer opened the web page |
| `expires_at` | timestamp | Authoritative timer — both kiosk and web compute countdown from this |
| `amount_usd` | float \| null | Set by kiosk when payment trigger fires |
| `amount_crypto` | float \| null | Set by kiosk when processor provides it (future step) |
| `payment_link` | string \| null | QR code content + web payment URL (from processor, future step) |
| `extended` | bool | `true` once customer uses "Add 1 minute" — button hidden after |

**Status transitions:**

```
waiting_for_vend
    │  payment trigger (A / B / C)
    ▼
payment_shown
    ├── processor confirms → paid
    └── expires_at reached → expired

waiting_for_vend
    └── expires_at reached → expired
```

---

## Kiosk-Side Implementation

### New file: `core/crypto_session.py`

**`CryptoSessionManager(QObject)`** — owns all crypto session state on the kiosk.

**Responsibilities:**
- Starts a Firestore `on_snapshot` listener on `/kiosks/{kiosk_id}/crypto_sessions/active` in a daemon thread; posts events back to Qt via an internal signal (thread-safe)
- On `waiting_for_vend` document arrival: sets `bus.crypto_mode = True`, `bus.crypto_coin = coin`, emits `bus.crypto_session_changed(session_dict)`, suppresses `_IdleScreen` on the Square Terminal
- Connects to `bus.payment_requested`; when `bus.crypto_mode` is `True` **or** `payment_type == "bitcoin"`:
  - Intercepts the payment (SquareClient returns early)
  - Calls placeholder payment processor (returns a stub link for now)
  - Posts Terminal QR action via `POST /v2/terminals/actions`
  - Writes `status: "payment_shown"`, `amount_usd`, `payment_link`, `expires_at: now+60s` to Firestore
  - Starts a `QTimer` set to fire at `expires_at - now` ms; timer is restarted whenever the Firestore `on_snapshot` delivers an updated `expires_at` (e.g. after the customer extends)
- On `expires_at` reached:
  - Cancels Terminal QR action via `POST /v2/terminals/actions/{id}/cancel`
  - Writes `status: "expired"` to Firestore
  - Clears `bus.crypto_mode`, `bus.crypto_coin`
  - Emits `bus.crypto_session_changed(None)`
  - Restores `_IdleScreen`
- On `status == "paid"` in Firestore:
  - Cancels Terminal QR action
  - Clears state
  - Emits `bus.crypto_session_changed(None)`

**Path C (direct, no web session):** When `bus.payment_requested` fires with `payment_type == "bitcoin"` and no active session, `CryptoSessionManager` creates a local-only session (does not require a web page to be open), writes a new `crypto_sessions/active` document, and proceeds identically to paths A/B.

### `core/bus.py` additions

```python
crypto_session_changed = pyqtSignal(object)  # session dict or None when cleared

# Plain attributes (checked synchronously, not signals):
crypto_mode = False   # True while a crypto session is active
crypto_coin = ""      # "BTC" | "ETH" | etc.
```

### `SquareClient` change (`core/square.py`)

One guard at the top of `_handle`:
```python
def _handle(self, tx_id, amount, payment_type):
    if bus.crypto_mode:
        return  # CryptoSessionManager intercepts this payment
```

### `_IdleScreen` change (`core/square.py`)

Pause idle QR screen during crypto sessions (not just during payments):
- Connect to `bus.crypto_session_changed`
- `_cancel_current()` when session becomes active
- `_show()` when session clears (same as payment done path)

### UI indicator

Connect to `bus.crypto_session_changed` in the header widget or dashboard.

| Session status | Indicator |
|---|---|
| `waiting_for_vend` | Amber pill: `⟳ CRYPTO · BTC` |
| `payment_shown` | Amber pill: `⏳ BTC PAYMENT` |
| `None` (cleared) | Pill hidden |

---

## Web Page Implementation (`kiosk-manager` repo)

**Route:** `app/enable-crypto/[kiosk_id]/page.tsx`

### UI states

**Initialising** (on page load)
- Verify kiosk exists in Firestore; show "Kiosk not found" if not
- If an existing `payment_shown` session is active for this kiosk, skip straight to State 3
- Otherwise show coin selector (BTC default, ETH / SOL / LTC) + **"Enable Crypto Mode" button**
- Session is written only when customer taps the button: `{ status: "waiting_for_vend", coin, session_id: uuid(), created_at: now, expires_at: now+60s, extended: false }`
- Coin is locked from this point — selector becomes read-only

**State 2 — `waiting_for_vend`**
- Message: "Kiosk is ready for crypto. Select your item within [countdown]."
- Countdown computed each second from `expires_at - now` (no client timer state)
- On countdown = 0: write `status: "expired"`

**State 3 — `payment_shown`**
- QR code rendered client-side from `payment_link`
- Shows: amount in USD, amount in coin (`amount_crypto`), coin label
- Countdown from `expires_at`
- "Need 1 more minute?" button — visible only if `extended == false`; on tap: write `expires_at: now+60s, extended: true`
- On countdown = 0: write `status: "expired"`

**State 4 — `expired`**
- Expired from State 2: "Session timed out. Scan the QR code to try again."
- Expired from State 3: "Time's up — kiosk is switching back to card payment mode."

**State 5 — `paid`**
- "✓ Payment accepted in [coin]!"

All state transitions driven by `onSnapshot` on the `crypto_sessions/active` document. No polling.

---

## What Is Out of Scope (Next Step)

- External crypto payment processor integration (BTCPay Server, OpenNode, Strike, etc.)
- Actual `payment_link` / `amount_crypto` generation — placeholder stub for now
- Processor webhook → Firestore `status: "paid"` write

---

## Files Changed

| File | Change |
|---|---|
| `core/crypto_session.py` | New — CryptoSessionManager |
| `core/bus.py` | Add `crypto_session_changed` signal + `crypto_mode` / `crypto_coin` attrs |
| `core/square.py` | Guard in `SquareClient._handle`; `_IdleScreen` connects to crypto session signal |
| `ui/header.py` (or `ui/screens/dashboard.py`) | Crypto mode indicator pill |
| `kiosk-manager: app/enable-crypto/[kiosk_id]/page.tsx` | New page |
