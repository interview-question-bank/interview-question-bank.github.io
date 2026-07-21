#!/usr/bin/env node
// Encrypt dist/index.html behind a password gate → gated index.html.
// AES-256-GCM, key from PBKDF2-SHA256 (310k iterations). Decryption happens
// in-browser via WebCrypto; the served file contains only ciphertext.
import { readFileSync, writeFileSync } from "node:fs";

const PASSWORD = process.argv[2];
if (!PASSWORD) { console.error("usage: gate.mjs <password> [in] [out]"); process.exit(1); }
const IN = process.argv[3] ?? "dist/index.html";
const OUT = process.argv[4] ?? "index.html";
const ITER = 310000;

const enc = new TextEncoder();
const salt = crypto.getRandomValues(new Uint8Array(16));
const iv = crypto.getRandomValues(new Uint8Array(12));
const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(PASSWORD), "PBKDF2", false, ["deriveKey"]);
const key = await crypto.subtle.deriveKey(
  { name: "PBKDF2", salt, iterations: ITER, hash: "SHA-256" },
  keyMaterial, { name: "AES-GCM", length: 256 }, false, ["encrypt"]);
const plaintext = readFileSync(IN);
const ciphertext = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext));

const b64 = (u8) => Buffer.from(u8).toString("base64");

const page = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Interview Question Bank — locked</title>
<style>
:root { --bg:#101410; --card:#181d18; --fg:#e8ece6; --soft:#b4bdb0; --faint:#7d867a;
        --line:#2a322a; --accent:#8fd436; --err:#ff7b6b; }
@media (prefers-color-scheme: light) {
  :root { --bg:#f7f8f7; --card:#ffffff; --fg:#1a1f1a; --soft:#4c554c; --faint:#7a837a;
          --line:#dde3dd; --accent:#4d8f00; --err:#c0392b; }
}
* { box-sizing:border-box; }
body { margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--fg);
  font:16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.gate { width:min(400px, calc(100vw - 40px)); background:var(--card); border:1px solid var(--line);
  border-radius:18px; padding:38px 34px 34px; text-align:center;
  box-shadow:0 1px 2px rgba(0,0,0,.25), 0 14px 44px rgba(0,0,0,.22); }
.lock { width:52px; height:52px; margin:0 auto 18px; border-radius:14px; display:grid; place-items:center;
  background:color-mix(in srgb, var(--accent) 16%, transparent); }
.lock svg { width:24px; height:24px; fill:none; stroke:var(--accent); stroke-width:2; stroke-linecap:round; }
h1 { font-size:19px; margin:0 0 6px; letter-spacing:-.01em; }
p  { margin:0 0 22px; color:var(--soft); font-size:14px; }
form { display:flex; gap:8px; }
input { flex:1; min-width:0; font:inherit; padding:10px 14px; border-radius:10px; border:1px solid var(--line);
  background:var(--bg); color:var(--fg); outline:none; letter-spacing:.12em; }
input:focus { border-color:var(--accent); box-shadow:0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
button { font:inherit; font-weight:650; padding:10px 18px; border-radius:10px; border:0; cursor:pointer;
  background:var(--accent); color:#0d120d; }
button:disabled { opacity:.55; cursor:wait; }
.msg { min-height:20px; margin-top:14px; font-size:13px; color:var(--err); }
.gate.shake { animation:shake .4s; }
@keyframes shake { 20%,60% { transform:translateX(-7px);} 40%,80% { transform:translateX(7px);} }
</style>
</head>
<body>
<main class="gate" id="gate">
  <div class="lock"><svg viewBox="0 0 24 24"><rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/></svg></div>
  <h1>Interview Question Bank</h1>
  <p>This site is password-protected. Enter the password to unlock.</p>
  <form id="form">
    <input id="pw" type="password" placeholder="Password" autocomplete="current-password" autofocus aria-label="Password">
    <button id="go" type="submit">Unlock</button>
  </form>
  <div class="msg" id="msg" role="alert"></div>
</main>
<script>
const SALT = Uint8Array.from(atob("${b64(salt)}"), c => c.charCodeAt(0));
const IV   = Uint8Array.from(atob("${b64(iv)}"), c => c.charCodeAt(0));
const DATA = "${b64(ciphertext)}";
const ITER = ${ITER};

async function decrypt(password) {
  const km = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey({ name:"PBKDF2", salt:SALT, iterations:ITER, hash:"SHA-256" },
    km, { name:"AES-GCM", length:256 }, false, ["decrypt"]);
  const ct = Uint8Array.from(atob(DATA), c => c.charCodeAt(0));
  const pt = await crypto.subtle.decrypt({ name:"AES-GCM", iv:IV }, key, ct);
  return new TextDecoder().decode(pt);
}

function reveal(html) {
  document.open(); document.write(html); document.close();
}

const form = document.getElementById("form"), pw = document.getElementById("pw"),
      go = document.getElementById("go"), msg = document.getElementById("msg"),
      gate = document.getElementById("gate");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = ""; go.disabled = true; go.textContent = "Unlocking…";
  try {
    const html = await decrypt(pw.value);
    sessionStorage.setItem("iqb-pw", pw.value);
    reveal(html);
  } catch {
    go.disabled = false; go.textContent = "Unlock";
    msg.textContent = "Wrong password — try again.";
    gate.classList.remove("shake"); void gate.offsetWidth; gate.classList.add("shake");
    pw.select();
  }
});

// auto-unlock within the same tab session
const saved = sessionStorage.getItem("iqb-pw");
if (saved) decrypt(saved).then(reveal).catch(() => sessionStorage.removeItem("iqb-pw"));
</script>
</body>
</html>
`;
writeFileSync(OUT, page);
console.log(`gated ${IN} (${plaintext.length} bytes) → ${OUT} (${page.length} bytes), pbkdf2 iters=${ITER}`);
