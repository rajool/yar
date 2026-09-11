---
title: Platform Reliability Review
subtitle: Incident patterns over the last two quarters and the remediation plan for the next
type: Engineering Report
kind: report
prepared_for: Architecture Council
author: Reliability Group
version: "2.1"
status: Final
confidentiality: Confidential
---

## 1. Summary

Availability held at **99.95%** across both quarters while the incident count
fell by a third. Two of the three severity-one incidents traced to the same
queue back-pressure defect, now fixed; the third was a certificate expiry that
the new inventory would have caught. The plan below spends the next quarter on
the two remaining single points of failure.

## 2. Incidents by quarter

| Severity | Q1 | Q2 | Change |
|---|---|---|---|
| Sev 1 | 2 | 1 | (1) |
| Sev 2 | 9 | 6 | (3) |
| Sev 3 | 31 | 22 | (9) |
| **Total** | **42** | **29** | **(13)** |

Numbers are right-aligned in tabular figures, the header is a small label, and
the bold last row is set as the total with a rule above and a double rule below.

## 3. Cost of the on-call rota

| Item | Amount (USD) | Note |
|---|---|---|
| Primary rota, 4 engineers | 96,000 | Two weeks on, six off |
| Secondary rota | 48,000 | Escalation only |
| Tooling and paging | 11,400 | Annual licences |
| **Total** | **155,400** | |

## 4. Remediation plan

| Workstream | Owner | Milestone |
|---|---|---|
| **Queue isolation** | Platform team | Per-tenant queues behind a limiter by end of quarter |
| **Certificate inventory** | Security | Automated renewal and a 30-day expiry alarm |
| **Read replicas** | Data | One replica per region, promoted by health check |

A text table keeps a hairline between rows; its bold labels are labels, not
totals.

## 5. What we will not do

- Rewrite the scheduler. Its two incidents came from the queue, not from it.
- Add a third region before the replicas are in place.
