---
name: source-claims
description: Verify and source the factual, market, or statistical claims in a draft (email, post, memo, proposal) so each one carries a hyperlink to the ORIGINAL independent source — not a vendor's own marketing page — backed by a concrete number. Searches the web for the real URL (never guesses or fabricates links), prefers primary reports / independent press over self-interested sources, and flags any claim it cannot back so the author can cut it or mark it an estimate. Use when asked to "source this", "back these claims with links", "add citations", "fact-check and link the claims", "هر ادعا رو با منبع و لینک پشتیبانی کن", "منبعِ اصلی برای این ادعاها", or before sending a claim-heavy email / publishing a data-backed post.
---

# source-claims — back every claim with a verified original source

Goal: take a draft (or a list of claims) and return each factual / market /
statistical claim **backed by a real, verified hyperlink to the original
independent source**, with a concrete number — so the writing is evidence-backed,
not assertion. The whole point is source-integrity: never invent a URL, and never
lean on a self-interested page for a market claim.

**This skill is invoke-only.** It runs when you ask it to source/verify claims;
it does not send or publish anything — it returns sourced claims for the author.

## 1) Pull out the claims
Read the draft and list every **factual / market / statistical** claim — anything
a reader could answer with "says who?" or "how much?". The author's opinions,
asks, and framing are not claims to source; skip them.

## 2) Verify + source each claim (the core)
For **each** claim:
1. Use `WebSearch` / `WebFetch` to find the source and the **exact, real URL**.
   **Never guess, fabricate, or approximate a link.** If you cannot reach a real
   source, do not cite one.
2. **Link the ORIGINAL independent source, not a self-interested one.** Preference:
   - A primary report/study/filing, or an independent outlet (reputable industry
     press, news, the original research).
   - A company's own page is acceptable **only** for a claim about that company's
     own product ("X ships feature Y"), never for a market/statistics claim — a
     party that benefits from the claim is a biased source.
3. Back the claim with a **specific number** (not "a lot / growing fast"). Where
   possible, use the audience's own figures — harder to dispute, fairer.
4. If a claim has no credible source → **cut it, or mark it explicitly as an
   estimate/assumption** (unlinked). Never dress an assumption as a sourced fact.

## 3) Return
Hand back, for the author to drop into their draft:
- Each claim with its **verified URL** (ready as an inline `<a href>` or a
  parenthetical), the **number**, and the **source name**.
- A short **"unsourced / flagged"** list: claims you could not back, and why — so
  the author cuts them or marks them estimates.
- Redirects that resolve to the real source (e.g. search-grounding redirects) are
  fine; the requirement is that the link reaches the genuine original.

## Special behaviors
- **Self-interest test:** if the only source for a market/stat claim is the party
  that profits from it, treat the claim as unsourced.
- **Source quality:** a primary/independent source beats a passing secondary
  mention; surface conflicting or low-confidence sources rather than presenting a
  contested figure as settled.
- **Currency:** for fast-moving claims prefer recent sources and note the date.

## Self-check
- [ ] Every cited URL was actually fetched/verified — none guessed or invented?
- [ ] Market/statistics claims link to an INDEPENDENT source, not a self-interested page?
- [ ] Each sourced claim carries a concrete number?
- [ ] Unsourced claims were flagged (cut or marked estimate), not silently dressed as fact?

## Dependencies
- **Tools:** `WebSearch`, `WebFetch` (plus `Read`/`Glob`/`Grep` to read the draft or local source files).
- **Pairs with:** any "write as <person>" voice skill and any drafting workflow that
  needs evidence backing — this skill supplies the sourced facts; the workflow
  decides voice, format, and delivery.
