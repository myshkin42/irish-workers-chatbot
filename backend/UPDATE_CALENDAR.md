# Irish Workers' Rights Chatbot — Update Calendar

## Monthly Routine

Run on the **1st of each month**:

```powershell
cd C:\Projects\irish-workers-chatbot\backend
python -m app.check_currency
```

Review any 🔄 CHANGED sources. If a source has changed:

```powershell
# 1. Download the updated document to your docs folder
# 2. Re-ingest it:
python -m app.reingest --file docs/guides/updated-doc.pdf --namespace guides --replace

# 3. Run the test suite to make sure nothing broke:
python -m app.test_retrieval
```

---

## Annual Calendar

### January
- **[CRITICAL] Minimum wage update** — new rate takes effect 1 Jan
  - Check: citizensinformation.ie/en/employment/.../minimum-wage/
  - Also check sub-minimum rates for under-20s
  - Re-ingest: `ci-minimum-wage.pdf` in guides namespace
  - Update any minimum wage figures in sector documents (EROs/SEOs)

- **Sick leave days** — may increase (5 → 7 → 10 planned progression)
  - Check: citizensinformation.ie sick leave page
  - Re-ingest if changed

### March/April
- **ERO/SEO rate reviews** — some sector orders update in spring
  - Check WRC ERO page
  - Construction SEO often reviewed around this time

### June
- **[WATCH] EU Pay Transparency Directive** — transposition deadline June 2026
  - If Ireland passes the Pay Transparency Bill, this will need:
    - New document ingested (the Act)
    - Updated Citizens Info pages
    - Possibly new code of practice from WRC

### October
- **Budget announcement** — may contain employment law changes
  - Minimum wage for following year announced
  - Any new employment legislation flagged
  - Social welfare rates (relevant to maternity/paternity benefit)

### December
- **EU Platform Workers Directive** — transposition deadline ~end 2026
  - Similar to Pay Transparency — watch for Irish implementation
  - Will affect gig economy workers (Deliveroo, Uber etc.)

---

## What to Re-ingest When

| Trigger | Documents to Update | Namespace |
|---------|-------------------|-----------|
| Minimum wage change | CI minimum wage page, NMW Act/SI | guides, statutory-instruments |
| Sick leave days change | CI sick leave page, Sick Leave Act guide | guides |
| New Code of Practice | The code itself | codes |
| ERO/SEO rate change | The specific order | sectors |
| New Act passed | The Act + CI explainer | acts, guides |
| EU directive transposed | New Act + EU summary update | acts, eu |
| CI page updated | The specific CI page | guides |
| WRC guide updated | The specific guide | guides |

---

## Re-ingest Workflow

```
1. Download updated document
2. python -m app.reingest --file <path> --namespace <ns> --replace
3. python -m app.test_retrieval           # regression check
4. python -m app.test_retrieval -q "relevant query"  # spot check
5. Test via the chat endpoint
6. Update KNOWLEDGE_BASE_UPDATED in main.py
```

---

## First Run Setup

Store baseline hashes (run once):
```powershell
python -m app.check_currency --reset
```

This stores the current state of all monitored URLs so future runs can detect changes.
