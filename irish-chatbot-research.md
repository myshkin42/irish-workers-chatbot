# Irish Workers' Rights Chatbot - Research & Document Inventory

## Executive Summary

This document outlines the research findings for building an Irish workers' rights chatbot. Unlike the Australian version (which has a complex federal/state system and industry-specific awards), Ireland has a simpler single-jurisdiction system but with its own unique structures like Joint Labour Committees (JLCs) and Sectoral Employment Orders (SEOs).

---

## Key Differences: Australia vs Ireland

| Aspect | Australia | Ireland |
|--------|-----------|---------|
| **Jurisdiction** | Federal + 6 states/2 territories | Single national jurisdiction |
| **Wage-setting** | 100+ industry awards | National minimum wage + 3 EROs + 3 SEOs |
| **Main body** | Fair Work Commission | Workplace Relations Commission (WRC) |
| **Safety body** | Safe Work Australia + state bodies | Health and Safety Authority (HSA) |
| **Appeal body** | Federal Court | Labour Court |
| **Union peak body** | ACTU | ICTU |
| **Official languages** | English only | English + Irish (Gaeilge) |

**Implication**: The Irish chatbot will be simpler to build - fewer namespaces, no state-based routing, no award detection. But we need bilingual support from day one.

---

## Primary Document Sources

### 1. Legislation (from irishstatutebook.ie)

All Acts are available in HTML and PDF. Most are in English only, with Irish translations available for some via acts.ie.

#### Core Employment Acts (Priority 1 - Must Have)

| Act | Description | Notes |
|-----|-------------|-------|
| **Unfair Dismissals Acts 1977-2015** | Protection against unfair dismissal | Most-queried topic (15% of WRC complaints) |
| **Organisation of Working Time Act 1997** | Hours, breaks, annual leave | Second most-queried (9% of complaints) |
| **Employment Equality Acts 1998-2015** | Discrimination on 9 grounds | 14% of WRC complaints |
| **National Minimum Wage Act 2000** | Minimum wage entitlements | 27% of complaints relate to pay |
| **Terms of Employment (Information) Acts 1994-2014** | Contract requirements | Core rights |
| **Payment of Wages Act 1991** | Pay slips, deductions | Core rights |
| **Redundancy Payments Acts 1967-2014** | Redundancy entitlements | Common query |
| **Minimum Notice and Terms of Employment Acts 1973-2005** | Notice periods | Common query |
| **Safety, Health and Welfare at Work Act 2005** | Workplace safety | HSA enforcement |
| **Workplace Relations Act 2015** | Established WRC | Procedural |

#### Protective Leave Acts (Priority 1)

| Act | Description |
|-----|-------------|
| **Maternity Protection Acts 1994-2004** | Maternity leave |
| **Parental Leave Acts 1998-2019** | Parental leave |
| **Paternity Leave and Benefit Act 2016** | Paternity leave |
| **Parent's Leave and Benefit Act 2019** | Parent's leave |
| **Carer's Leave Act 2001** | Carer's leave |
| **Adoptive Leave Acts 1995-2005** | Adoptive leave |
| **Sick Leave Act 2022** | Statutory sick pay (NEW - 5 days in 2025) |

#### Other Important Acts (Priority 2)

| Act | Description |
|-----|-------------|
| **Protected Disclosures Acts 2014-2022** | Whistleblower protection |
| **Protection of Employees (Part-Time Work) Act 2001** | Part-time worker rights |
| **Protection of Employees (Fixed-Term Work) Act 2003** | Fixed-term contracts |
| **Protection of Employees (Temporary Agency Work) Act 2012** | Agency workers |
| **Employment (Miscellaneous Provisions) Act 2018** | Banded hours, zero-hour ban |
| **Work Life Balance and Miscellaneous Provisions Act 2023** | Flexible/remote work requests |
| **Industrial Relations Acts 1946-2015** | Collective bargaining, JLCs |
| **Employment Permits Acts 2003-2024** | Work permits |

#### Statutory Instruments (Priority 2)

| S.I. | Description |
|------|-------------|
| **S.I. No. 472/2025** | National Minimum Wage Order 2025 (€14.15 from Jan 2026) |
| **S.I. No. 92/2024** | Right to Request Flexible/Remote Working Code |
| **S.I. No. 674/2020** | Code of Practice - Bullying at Work |
| **Safety, Health and Welfare at Work (General Application) Regulations 2007-2023** | HSA regulations |

---

### 2. WRC Publications (from workplacerelations.ie)

**Available in English + Irish (Gaeilge):**
- Employment Law Explained (PDF - excellent summary document)
- Guide to Employment, Labour and Equality Law
- Guide to the WRC

**Available in multiple languages:**
- English, Irish, Polish, Romanian, Russian, Spanish, Ukrainian, Portuguese
- Topics: Seasonal workers, domestic workers, WRC inspections, adjudication hearings

**Codes of Practice (all available in English + Irish):**
- Right to Request Flexible/Remote Working (2024)
- Prevention and Resolution of Bullying at Work (2020)
- Right to Disconnect (2021)
- Grievance and Disciplinary Procedures
- Longer Working
- Protecting Persons Employed in Other People's Homes
- Sunday Working in Retail
- Victimisation
- Harassment (Employment Equality Act)

---

### 3. HSA Publications (from hsa.ie)

**Key documents:**
- Short Guide to Safety, Health and Welfare at Work Act 2005
- Risk Assessment Guidelines
- Sector-specific guides (construction, agriculture, healthcare, retail)
- Code of Practice for Chemical Agents
- Code of Practice for Preventing Injury in Agriculture
- Bullying guidance (joint with WRC)

---

### 4. Citizens Information (from citizensinformation.ie)

**Excellent plain-language guides on:**
- All employment topics
- Available in English + Irish (Gaeilge)
- Regularly updated
- Well-structured for chunking

**Key sections:**
- Employment rights and conditions
- Employment rights and duties
- Pay and employment
- Leave and holidays
- Equality in work
- Unemployment and redundancy
- Enforcement and redress

---

### 5. Sector-Specific: Employment Regulation Orders & Sectoral Employment Orders

#### Currently Active EROs (Joint Labour Committees)

| Sector | Current Order | Min Wage |
|--------|--------------|----------|
| **Contract Cleaning** | S.I. No. 608/2020 (as amended 2024) | Higher than NMW |
| **Security Industry** | S.I. No. 319/2024 | Higher than NMW |
| **Early Years/Childcare** | S.I. No. 477-478/2025 | Higher than NMW |

#### Currently Active SEOs (Sectoral Employment Orders)

| Sector | Current Order |
|--------|--------------|
| **Construction** | SEO 2024 (updated Aug 2025) |
| **Mechanical Engineering Building Services** | SEO 2018 |
| **Electrical Contracting** | SEO |

**Note:** These are Ireland's equivalent of Australian awards - but there are only 6 active ones vs 100+ in Australia. Much simpler!

---

## Union Information

### Should We Include Union Info?

**Arguments FOR:**
1. Workers often ask "how do I join a union?"
2. Unions are a primary source of workplace advice
3. ICTU and unions are stakeholders we may want to approach for support
4. 35% of Irish workforce is unionised (higher than Australia)
5. Union-related dismissal is automatically unfair under law

**Arguments AGAINST:**
1. Union websites change frequently (stale data risk)
2. Could be seen as endorsing specific unions
3. Membership costs/benefits change regularly

**RECOMMENDATION:** Include basic union information:
- What unions do
- How to join (general process)
- Which unions cover which sectors (factual, not promotional)
- Link to ICTU's "find your union" tool
- DO NOT include: membership costs, current campaigns, political positions

### Main Unions by Sector

| Union | Membership | Sectors |
|-------|------------|---------|
| **SIPTU** | ~173,000 | General - healthcare, retail, hospitality, transport, construction, manufacturing |
| **Fórsa** | ~89,000 | Public sector, state agencies, aviation |
| **INMO** | ~39,000 | Nurses and midwives |
| **Connect** | ~39,000 | Technical, construction, engineering |
| **Mandate** | ~33,000 | Retail workers |
| **Unite** | ~21,000 (ROI) | General (UK-based) |
| **INTO** | - | Primary teachers |
| **TUI** | - | Second-level teachers, lecturers |
| **ASTI** | - | Secondary teachers |
| **IMO** | - | Doctors |

---

## Language Strategy

### Current WRC Language Availability

| Language | Materials Available |
|----------|-------------------|
| **English** | Everything |
| **Irish (Gaeilge)** | Core guides, codes of practice |
| **Polish** | Key employment rights docs |
| **Ukrainian** | Employment rights for Ukrainian nationals |
| **Russian** | Employment Law Explained |
| **Romanian** | Seasonal workers, domestic workers |
| **Portuguese** | Key guides, inspections |
| **Spanish** | Limited materials |
| **Bulgarian** | Seasonal workers |
| **Latvian** | Seasonal workers |
| **Lithuanian** | Some materials |
| **Chinese** | Domestic workers, basic guides |
| **French** | Limited materials |
| **Hindi** | Domestic workers |
| **Filipino/Tagalog** | Employment Law Explained |

### Recommendation for Chatbot

**Phase 1 (Launch):**
- English only
- System prompt instructs to respond in user's language if asked
- But underlying knowledge base is English

**Phase 2 (If demand exists):**
- Irish (Gaeilge) - constitutional requirement, good optics
- Polish - largest migrant worker population

**Rationale:**
- The Australian multi-language feature was never properly tested
- The "minimum wage" translation issue suggests LLM translation alone isn't reliable for legal concepts
- Better to do one language well than seven poorly
- The WRC website already has Google Translate for basic needs

---

## Document Gathering Plan

### Priority 1: Core Corpus (Week 1-2)

| Source | Documents | Format | Effort |
|--------|-----------|--------|--------|
| irishstatutebook.ie | 15 core Acts | HTML/PDF | Low - direct download |
| WRC | Employment Law Explained | PDF | Low |
| WRC | All Codes of Practice (10) | PDF | Low |
| WRC | Guide to Employment Law | PDF | Low |
| HSA | Safety Act summary guide | PDF | Low |
| Citizens Information | ~50 employment pages | HTML scrape | Medium |

**Estimated documents: ~80**

### Priority 2: Sector-Specific (Week 2-3)

| Source | Documents | Format | Effort |
|--------|-----------|--------|--------|
| Labour Court | 3 EROs, 3 SEOs | PDF | Low |
| HSA | 10-15 sector guides | PDF | Low |
| WRC | JLC information | HTML | Low |

**Estimated documents: ~25**

### Priority 3: Supplementary (Week 3-4)

| Source | Documents | Format | Effort |
|--------|-----------|--------|--------|
| ICTU | Union overview, FAQ | HTML | Low |
| Individual unions | Basic "about" pages | HTML | Medium |
| IHREC | Discrimination guides | PDF | Low |

**Estimated documents: ~20**

### Total Estimated Corpus: ~125 documents
(vs ~400 for Australian version - much more manageable!)

---

## Key Questions the Chatbot Must Answer Well

Based on WRC complaint statistics and common queries:

### Top 10 Query Categories

1. **Pay issues** (27% of WRC complaints)
   - "What is the minimum wage?"
   - "Can my employer deduct from my wages?"
   - "I haven't been paid for overtime"

2. **Unfair dismissal** (15%)
   - "I was fired without warning"
   - "Can I claim unfair dismissal?"
   - "What is constructive dismissal?"

3. **Discrimination** (14%)
   - "I'm being treated differently because of my age/gender/disability"
   - "What are the 9 grounds of discrimination?"

4. **Working time** (9%)
   - "How many hours can I work per week?"
   - "What breaks am I entitled to?"
   - "Can my employer change my hours?"

5. **Terms of employment** (9%)
   - "Do I need a written contract?"
   - "My employer changed my contract without asking"

6. **Annual leave**
   - "How many holidays do I get?"
   - "Can my employer refuse my leave request?"

7. **Sick leave** (NEW - Sick Leave Act 2022)
   - "Am I entitled to paid sick leave?"
   - "How many sick days do I get?"

8. **Bullying and harassment**
   - "I'm being bullied at work"
   - "What can I do about harassment?"

9. **Redundancy**
   - "Am I entitled to redundancy pay?"
   - "Is my redundancy genuine?"

10. **Making a complaint**
    - "How do I complain to the WRC?"
    - "What's the time limit for complaints?"

---

## Technical Considerations

### Namespace Structure (Proposed)

```
irish-workers-chatbot/
├── acts/               # Primary legislation
├── regulations/        # Statutory instruments
├── codes/              # WRC codes of practice
├── guides/             # WRC, HSA, Citizens Info guides
├── eros-seos/          # Employment Regulation Orders, Sectoral Orders
├── unions/             # Basic union information
└── procedures/         # How to make complaints, WRC process
```

**Note:** No state-based namespaces needed (unlike Australian version)

### Metadata Fields

```python
{
    "display_name": str,      # Human-readable title
    "doc_type": str,          # act, regulation, code, guide, ero, seo
    "year": int,              # Year of enactment/publication
    "source": str,            # wrc, hsa, irishstatutebook, citizensinfo
    "topic": str,             # pay, dismissal, leave, safety, discrimination
    "sector": str | None,     # cleaning, security, construction, etc.
    "language": str,          # en, ga (Irish)
}
```

### Query Expansion (Irish-specific)

```python
IRISH_EXPANSIONS = {
    r'\bwrc\b': 'workplace relations commission',
    r'\bhsa\b': 'health safety authority',
    r'\bictu\b': 'irish congress trade unions',
    r'\bsiptu\b': 'services industrial professional technical union',
    r'\binmo\b': 'irish nurses midwives organisation',
    r'\bjlc\b': 'joint labour committee',
    r'\bero\b': 'employment regulation order',
    r'\bseo\b': 'sectoral employment order',
    r'\bihrec\b': 'irish human rights equality commission',
}
```

---

## Risk Assessment

### High Risk Areas (Need Extra Care)

1. **Minimum wage complexity**
   - Sub-minimum rates for under-20s still exist (unlike what EU directive recommended)
   - ERO rates differ by sector
   - Easy to give wrong figure

2. **Sick leave (new law)**
   - Sick Leave Act 2022 is new and evolving
   - 5 days in 2025, planned to increase
   - Many workers don't know about it

3. **Discrimination**
   - 9 grounds in Ireland (vs 5 in Australia)
   - Traveller community is protected ground (unique to Ireland)
   - Easy to miss nuances

4. **Time limits**
   - 6 months for most WRC complaints
   - 12 months with "reasonable cause"
   - Missing deadline = case dismissed

### Medium Risk Areas

1. **Probation periods**
   - 12 months before unfair dismissal rights (with exceptions)
   - Often misunderstood

2. **Fixed-term contracts**
   - 4-year rule for conversion to permanent
   - Complex rules

3. **Agency workers**
   - Equal treatment rights after day 1
   - But which employer is responsible?

---

## Next Steps

1. **Document gathering** - Start downloading PDFs and scraping HTML
2. **Corpus review** - Check quality, identify gaps
3. **Chunking strategy** - Adapt Australian ingest pipeline
4. **System prompt** - Write Ireland-specific version
5. **Test queries** - Build test set from common questions
6. **Soft launch** - Deploy and iterate

---

## Appendix: Useful URLs

### Official Sources
- WRC: https://www.workplacerelations.ie
- HSA: https://www.hsa.ie
- Irish Statute Book: https://www.irishstatutebook.ie
- Citizens Information: https://www.citizensinformation.ie
- Labour Court: https://www.labourcourt.ie
- IHREC: https://www.ihrec.ie

### Union Sources
- ICTU: https://www.ictu.ie
- SIPTU: https://www.siptu.ie
- Fórsa: https://www.forsa.ie
- INMO: https://www.inmo.ie
- Mandate: https://www.mandate.ie
- Connect: https://www.connectunion.ie

### Other Useful Sources
- MRCI (Migrant Rights Centre Ireland): https://www.mrci.ie
- FLAC (Free Legal Advice Centres): https://www.flac.ie
- Employment Rights Ireland (blog): https://employmentrightsireland.com

---

---

## EU Legislation

This is crucial. Ireland is an EU member state, so EU law is a fundamental layer of employment rights. Most Irish employment legislation is either:
1. **Transposing EU Directives** (implementing EU requirements into Irish law), or
2. **Going beyond EU minimums** (Ireland often provides more than the minimum)

### How EU Law Works in Ireland

| Type | Description | Example |
|------|-------------|---------|
| **Regulations** | Apply directly, no Irish legislation needed | GDPR |
| **Directives** | Must be transposed into Irish law | Working Time Directive → Organisation of Working Time Act 1997 |
| **Case Law** | CJEU decisions binding on Irish courts | Tyco case on travel time |

### Key EU Directives Already Transposed

| EU Directive | Irish Implementation | Notes |
|--------------|---------------------|-------|
| **Working Time Directive 2003/88/EC** | Organisation of Working Time Act 1997 | 48-hour week, rest breaks, annual leave |
| **Equal Pay Directive 75/117/EEC** | Employment Equality Acts 1998-2015 | Equal pay for equal work |
| **Equal Treatment Directive 2006/54/EC** | Employment Equality Acts | Gender discrimination |
| **Race Equality Directive 2000/43/EC** | Employment Equality Acts | Race discrimination |
| **Framework Employment Directive 2000/78/EC** | Employment Equality Acts | Age, disability, religion, sexual orientation |
| **Fixed-Term Work Directive 99/70/EC** | Protection of Employees (Fixed-Term Work) Act 2003 | 4-year conversion rule |
| **Part-Time Work Directive 97/81/EC** | Protection of Employees (Part-Time Work) Act 2001 | Equal treatment |
| **Agency Workers Directive 2008/104/EC** | Protection of Employees (Temporary Agency Work) Act 2012 | Day-1 equal treatment |
| **Pregnant Workers Directive 92/85/EEC** | Maternity Protection Acts 1994-2004 | 14 weeks minimum maternity |
| **Parental Leave Directive 2010/18/EU** | Parental Leave Acts 1998-2019 | Replaced by Work-Life Balance Directive |
| **Information & Consultation Directive 2002/14/EC** | Employees (Provision of Information and Consultation) Act 2006 | Works councils |
| **Collective Redundancies Directive 98/59/EC** | Protection of Employment Acts 1977-2014 | 30-day consultation |
| **Transfer of Undertakings Directive 2001/23/EC** | European Communities (Protection of Employees on Transfer of Undertakings) Regulations 2003 | TUPE rights |
| **Posting of Workers Directive 96/71/EC (revised 2018)** | Posted workers regulations | Cross-border workers |
| **Transparent and Predictable Working Conditions Directive 2019/1152** | European Union (Transparent and Predictable Working Conditions) Regulations 2022 | Contract info, probation limits |
| **Whistleblowing Directive 2019/1937** | Protected Disclosures (Amendment) Act 2022 | Expanded protections |

### Recently Transposed / In Progress

| EU Directive | Status in Ireland | Deadline | Key Changes |
|--------------|-------------------|----------|-------------|
| **Work-Life Balance Directive 2019/1158** | Transposed (Work Life Balance Act 2023) | Was Aug 2022 (Ireland fined €1.54m for delay) | Paternity leave, flexible working requests, carers' leave |
| **Adequate Minimum Wages Directive 2022/2041** | In progress | Nov 2024 | Collective bargaining coverage, minimum wage adequacy |
| **Pay Transparency Directive 2023/970** | In progress (Pay Transparency Bill) | June 2026 | Salary range disclosure, ban on pay history questions, joint pay assessments |
| **Platform Workers Directive 2024/2831** | Not yet started | ~End 2026 | Presumption of employment for gig workers, algorithm transparency |

### Upcoming EU Legislation to Watch

#### 1. Pay Transparency Directive (June 2026)
**Big deal for workers.** Key changes:
- Salary range must be in job ads or disclosed before interview
- Employers cannot ask about salary history
- Workers can request average pay of colleagues doing same work
- Gender pay gap reporting expanded (by job category)
- 5%+ unexplained gap triggers mandatory joint pay assessment
- Burden of proof shifts to employer in equal pay claims
- Ban on pay secrecy clauses

**Ireland already has:** Gender Pay Gap reporting (since 2022), but will need updates.

#### 2. Platform Workers Directive (~End 2026)
**Affects gig economy workers (Deliveroo, Uber, etc.):**
- Presumption of employment when "control and direction" present
- Burden on platform to prove worker is genuinely self-employed
- Algorithm transparency - workers can contest automated decisions
- Can't be fired by algorithm alone
- Access to personal data restricted

**Ireland context:** Already has Code of Practice on determining employment status, but this strengthens it significantly.

#### 3. Adequate Minimum Wages Directive
- Requires member states where collective bargaining covers <80% of workers to create action plans
- Ireland is at ~35% coverage, so this applies
- Must ensure minimum wages are "adequate" (60% of median wage is benchmark)
- Ireland already moving toward "living wage" (€14.80) so mostly compliant

### CJEU (Court of Justice of the European Union) Cases Relevant to Ireland

| Case | Impact |
|------|--------|
| **Tyco (2015)** | Travel time to first/last customer counts as working time for workers without fixed workplace |
| **King v Sash Window (2017)** | Workers can carry over untaken annual leave if employer prevented them taking it |
| **Kreuziger (2018)** | Employers must encourage workers to take leave; can't just lose it |
| **Bauer (2018)** | Annual leave entitlement survives death - payable to estate |
| **Federación de Servicios (2018)** | Employers must have system to record daily working time |
| **Joined Cases on On-Call (2021)** | On-call time at employer's premises = working time |

### GDPR and Employment

The **General Data Protection Regulation** applies directly and affects:
- Employee data collection and storage
- Monitoring employees (email, CCTV, location tracking)
- Subject access requests (employees can request their data)
- Data breach notification
- Right to be forgotten (limited in employment context)

Ireland's Data Protection Commission (DPC) has issued guidance on employee monitoring.

### What This Means for the Chatbot

**Must include:**
1. References to EU origin of rights where relevant ("Under the Working Time Directive, implemented in Ireland by the Organisation of Working Time Act 1997...")
2. Current minimum standards from EU law
3. Upcoming changes (Pay Transparency, Platform Workers)
4. CJEU case law on key issues (travel time, annual leave carry-over)

**System prompt should:**
- Acknowledge EU foundation of Irish employment law
- Note where Ireland goes beyond EU minimums
- Flag upcoming changes that workers should know about
- Explain that CJEU decisions are binding on Irish courts

**Document corpus should include:**
- Key EU directives (working time, equality, etc.) - for reference
- Citizens Information pages on EU rights
- WRC guidance referencing EU law
- Upcoming directive summaries

---

## Summary: Full Document Inventory

### Core Irish Sources (~125 documents)
- 15 core Acts
- 10 Codes of Practice
- 6 EROs/SEOs
- ~50 Citizens Information pages
- ~20 WRC guides
- ~15 HSA guides
- ~10 union overview pages

### EU Sources (~25 documents)
- 5 key current directives (working time, equality, etc.)
- 3 upcoming directives (summaries)
- 10 CJEU case summaries
- 5 EU implementation guides

### Total: ~150 documents

This is very manageable compared to the Australian version's 400+ documents.

---

*Document prepared: January 2026*
*Author: Claude (with Eamon)*
