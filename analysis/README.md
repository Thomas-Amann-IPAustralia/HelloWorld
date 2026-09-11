# ai_referral_ctr.xlsx — validation and charts

## What was checked

`validate_ai_referral_ctr.py` rebuilds every formula cell in the workbook from the
`Sessions` source rows and compares the result against the value Excel had cached.
Run it from the repository root:

```
python analysis/validate_ai_referral_ctr.py
```

Covered: every `SUMIFS`, `SUBTOTAL`, `AVERAGEIFS`, `MINIFS`/`MAXIFS`, share and CTR
cell across 104 page rows, 121 day rows, 18 week rows and 4 referrer rows, plus the
date parts, ISO weeks, weekday/weekend flags, source-coverage flags and the
`Sessions!J` de-duplication flag.

**Result: zero disagreements.** No error cells, correct `_xlfn.` prefixes, and the
totals use `SUBTOTAL` so filtered CTRs genuinely reflow.

## What the arithmetic does not fix

| | Where | Issue |
|---|---|---|
| Overstated | `Weekly!K19` | Week 37 reports 16.0% CTR. 19 of its 36 sessions fall on 9–11 Sep, days with no Bing citations. Coverage-matched: 7.6%. Week 20 has the mirror-image problem: 0.77% reported, 1.47% matched. |
| Overstated | `README!B8`, `Pages!K106` | The headline 4.81% divides 443 sessions (15 May – 11 Sep) by 9,202 citations (14 May – 8 Sep). Over the 117 shared days it is 424 ÷ 10,342 = 4.10%. |
| Wrong premise | `README!B9`, `Pages!L106` | The "Copilot-only, apples-to-apples" CTR divides 3 Copilot sessions by all 9,202 Bing citations — which span Copilot, Bing AI summaries and partner integrations. One surface over three. |
| Read with care | `Pages!K2:K105` | 7 of 59 pages exceed 50% CTR and two exceed 100% (233%, 200%). Page-level CTR carries no signal below ~100 citations. |
| Understated | `README!B30` | 30 July is 609 citations — 7.4× the median day (82.5), not "roughly six times". Excluding it moves all-period CTR from 4.23% to 4.49%. |
| Understated | `README!B24` | 281 of 363 ChatGPT rows (77%) have a raw landing URL differing from its canonical form, not "roughly a third". |
| Mislabelled | `Weekly!L20` | Headed "mean of daily CTRs" but computes the mean of 18 weekly means, weighting a 4-day week like a 7-day one. |
| Mislabelled | `Sessions` grain | Documented as page-by-day-by-referrer; 29 key combinations appear twice, separated only by `raw_landing_url`. Totals are unaffected; joins assuming uniqueness will double. |
| Mislabelled | `Pages!R106` | Sums per-page day counts to 368, double-counting days. The site saw sessions on 98 distinct dates. |

Confirmed accurate: the ~12% reconciliation gap between the two Bing exports
(10,465 by day vs 9,202 by page = 12.07%), the two truncated-URL 404 landings,
the page counts (88 cited, 75 landed), and all four referrer totals.

## Charts

`ai_referral_ctr_audit.html` is a standalone page — no build step, no network
dependency beyond a webfont — with six charts covering the daily series and its
30 July outlier, the three defensible weekly CTRs, citation share against session
share per page, the log-log page scatter, the referrer/citation-surface mismatch,
and the outer-join coverage split.
