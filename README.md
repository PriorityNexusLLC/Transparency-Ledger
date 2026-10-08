# Priority Nexus Transparency Ledger

**Systems Assurance Forensic Investigation & Design** · *Identity · Transparency · Integrity*

Everything Priority Nexus LLC adds, edits, corrects, reviews, deletes or publishes, across all its projects, in
one append-only record. We have nothing to hide from our mistakes: corrections and deletions are listed by name
every month.

- **[LEDGER.md](LEDGER.md):** every entry, oldest first. One row each: date · action · project · what ·
  fingerprint · note · chain.
- **[STATS](STATS):** a one-page summary for each month, published on the 1st: counts per action, every
  correction and deletion by name, and whether the chain is intact.

## How it stays honest
- **Only added to.** A mistake is fixed by a new *Corrected* row, never by changing an old one.
- **Chained.** Each row's chain value is built from the row before it. Change or remove any past row and every
  later value breaks. Check it yourself: `python ledger.py verify` (Python 3, nothing to install).
- **History locked.** This repository refuses rewrites of its history, including from its owner.
- **Fingerprints.** Each row carries a fingerprint (SHA-256) of the file, commit or report it refers to.
- **Fair to others.** Reports not yet published are listed without their subject, so no one is named before they've
  had a chance to respond; the name appears when the report is published, and the fingerprint shows it's the same one.

Projects covered: [SCR-01 Protocol](https://github.com/PriorityNexusLLC/SCR-01-Protocol) ·
[Assumption-Check](https://github.com/PriorityNexusLLC/Assumption-Check-) ·
[Prion Research Notes](https://github.com/PriorityNexusLLC/Prion-Protien-Research) ·
[Deterministic Governance & Circuit-Breaker Architecture](https://github.com/PriorityNexusLLC/Deterministic-Governance-Circuit-Breaker-Architecture) ·
[PNMaster-Graph](https://github.com/PriorityNexusLLC/PNMaster-Graph) ·
[website](https://prioritynexusllc.github.io) · this ledger.

Josie Anderson, Architecture & Systems Lead · theaistherapist@gmail.com · © 2026 Priority Nexus LLC · Apache-2.0
