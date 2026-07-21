# Interview Question Bank

A curated, quality-ranked bank of technical and behavioral interview questions for systems, networking, ML, infrastructure, and AI/LLM engineering roles — with reference solutions and interviewer keys.

**Live site:** https://dan8901.github.io/interview-question-bank/

The site is password-protected: the entire page is AES-256-GCM-encrypted (key derived from the password with PBKDF2-SHA256, 310k iterations) and decrypted in the browser via WebCrypto. The published file contains only ciphertext.

- `build.py` — generates the single-file static site (`dist/index.html`) from the markdown sources (kept privately, not in this repo)
- `gate.mjs` — encrypts the built site behind the password gate
- `index.html` — the published (encrypted) site

To rebuild after editing the sources: `python3 build.py`, then `node gate.mjs <password>`.
