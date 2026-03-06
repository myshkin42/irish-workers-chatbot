"""
Irish Workers' Rights Chatbot - Query Preprocessing

Maps conversational language to legal terminology for better retrieval.
Also expands common Irish employment law abbreviations.

Tier 1 of a tiered retrieval strategy:
  Tier 1: Static mapping (this module) - free, instant
  Tier 2: LLM query rewrite - cheap API call, only on retrieval misses
  Tier 3: Honest "I don't know" - already built into main.py
"""
import re
from typing import Tuple, List, Dict


# ----------------------------------------------------------------------------
# Tier 1a: Abbreviation Expansions
# Irish employment law acronyms → full terms
# These REPLACE in-place (you don't want both "WRC" and the expansion)
# ----------------------------------------------------------------------------
ABBREVIATION_EXPANSIONS: List[Tuple[re.Pattern, str, str]] = [
    # (compiled_regex, replacement, friendly_label)
    (re.compile(r'\bwrc\b', re.IGNORECASE), 'workplace relations commission', 'wrc'),
    (re.compile(r'\bhsa\b', re.IGNORECASE), 'health and safety authority', 'hsa'),
    (re.compile(r'\bictu\b', re.IGNORECASE), 'irish congress of trade unions', 'ictu'),
    (re.compile(r'\bsiptu\b', re.IGNORECASE), 'services industrial professional technical union', 'siptu'),
    (re.compile(r'\binmo\b', re.IGNORECASE), 'irish nurses and midwives organisation', 'inmo'),
    (re.compile(r'\bjlc\b', re.IGNORECASE), 'joint labour committee', 'jlc'),
    (re.compile(r'\bero\b', re.IGNORECASE), 'employment regulation order', 'ero'),
    (re.compile(r'\bseo\b', re.IGNORECASE), 'sectoral employment order', 'seo'),
    (re.compile(r'\bihrec\b', re.IGNORECASE), 'irish human rights and equality commission', 'ihrec'),
    (re.compile(r'\bmrci\b', re.IGNORECASE), 'migrant rights centre ireland', 'mrci'),
    (re.compile(r'\bflac\b', re.IGNORECASE), 'free legal advice centres', 'flac'),
    (re.compile(r'\bnmw\b', re.IGNORECASE), 'national minimum wage', 'nmw'),
    (re.compile(r'\btupe\b', re.IGNORECASE), 'transfer of undertakings protection of employment', 'tupe'),
    (re.compile(r'\bgdpr\b', re.IGNORECASE), 'general data protection regulation', 'gdpr'),
    (re.compile(r'\bppe\b', re.IGNORECASE), 'personal protective equipment', 'ppe'),
    (re.compile(r'\bcjeu\b', re.IGNORECASE), 'court of justice european union', 'cjeu'),
]


# ----------------------------------------------------------------------------
# Tier 1b: Conversational → Legal Term Mapping
# What workers say → what the documents say
#
# These are APPENDED to the query, not replaced, so the original
# conversational terms still contribute to the embedding.
#
# Patterns are compiled at module load for efficiency.
# ----------------------------------------------------------------------------
_CONVERSATIONAL_RAW: List[Tuple[str, str, str]] = [
    # (pattern_string, legal_terms_to_append, friendly_label)

    # --- Dismissal / Termination ---
    (r'\b(fired|got fired|been fired)\b', 'unfair dismissal termination of employment', 'fired'),
    (r'\b(sacked|got sacked|been sacked|got the sack)\b', 'unfair dismissal termination of employment', 'sacked'),
    (r'\b(let go|been let go)\b', 'dismissal redundancy termination', 'let-go'),
    (r'\b(lost my job)\b', 'dismissal redundancy termination of employment', 'lost-job'),
    (r'\b(booted|kicked out|thrown out)\b', 'dismissal termination', 'booted'),
    (r'\b(pushed out|managed out)\b', 'constructive dismissal', 'pushed-out'),
    (r'\b(forced to resign|forced to quit|had to quit)\b', 'constructive dismissal', 'forced-resign'),
    (r'\b(got rid of me|trying to get rid of me)\b', 'constructive dismissal unfair dismissal', 'got-rid'),
    (r'\b(no warning|without warning)\b', 'unfair dismissal fair procedures minimum notice', 'no-warning'),
    (r'\b(on the spot)\b', 'summary dismissal fair procedures', 'on-the-spot'),
    (r'\b(written up)\b', 'disciplinary warning procedure', 'written-up'),
    (r'\b(disciplinary)\b', 'disciplinary procedure fair procedures code of practice', 'disciplinary'),

    # --- Pay & Wages ---
    (r"\b(not paid|not being paid|haven'?t been paid|havent been paid)\b", 'payment of wages non-payment', 'not-paid'),
    (r'\b(short paid|underpaid|short on my wages)\b', 'payment of wages underpayment minimum wage', 'underpaid'),
    (r'\b(wage theft)\b', 'non-payment of wages deduction', 'wage-theft'),
    (r'\b(docked pay|docked wages)\b', 'deduction from wages payment of wages act', 'docked-pay'),
    (r'\b(owed money|owed wages|missing wages)\b', 'non-payment of wages arrears', 'owed-wages'),
    (r'\b(holding my pay|withholding)\b', 'withholding wages unlawful deduction payment of wages', 'holding-pay'),
    (r'\b(cash in hand|cash job|paid cash)\b', 'payment of wages payslip employment status', 'cash-in-hand'),
    (r"\b(no payslip|no pay ?slip)\b", 'payslip payment of wages act', 'no-payslip'),
    (r'\b(tips?|gratuities|keeping the tips)\b', 'tips gratuities distribution payment of wages', 'tips'),
    (r'\b(holiday pay)\b', 'annual leave pay holiday pay entitlement', 'holiday-pay'),
    (r'\b(sunday rate|sunday premium)\b', 'sunday working premium organisation of working time', 'sunday-rate'),

    # --- Working Hours & Breaks ---
    (r'\b(too many hours|working too much|crazy hours|long shifts)\b', 'organisation of working time maximum hours 48 hour week working hours', 'too-many-hours'),
    (r'\b(\d+\s*hours?\s*(a|per)\s*week)\b', 'organisation of working time maximum working hours 48 hour week', 'hours-per-week'),
    (r"\b(no breaks?|not getting breaks?|no lunch break)\b", 'rest periods breaks organisation of working time', 'no-breaks'),
    (r'\b(no day off|no days off)\b', 'rest periods weekly rest organisation of working time', 'no-day-off'),
    (r'\b(back to back shifts?|no turnaround)\b', 'rest periods daily rest 11 hours organisation of working time', 'back-to-back'),
    (r'\b(overtime)\b', 'working time hours overtime organisation of working time act', 'overtime'),
    (r'\b(zero[- ]?hours?|0[- ]?hours?)\b', 'banded hours zero hour contracts employment miscellaneous provisions', 'zero-hours'),
    (r'\b(changed? my hours|changed? my roster|cut my shifts?|reduced my hours)\b', 'terms of employment change of hours banded hours zero hour contracts changes to employment contract', 'changed-hours'),
    (r'\b(no rota|late rota|no roster)\b', 'rostering notice working time schedule', 'no-rota'),

    # --- Leave & Holidays ---
    (r'\b(holidays?|annual leave)\b', 'annual leave organisation of working time entitlement', 'holidays'),
    (r'\b(days off|time off)\b', 'annual leave entitlement', 'time-off'),
    (r"\b(sick days?|off sick|called in sick|out sick)\b", 'sick leave statutory sick pay sick leave act', 'sick'),
    (r"\b(doctor'?s? cert|sick cert|medical cert)\b", 'medical certificate sick leave', 'sick-cert'),
    (r'\b(stress leave)\b', 'sick leave mental health', 'stress-leave'),
    (r'\b(pregnant|having a baby|expecting)\b', 'maternity leave maternity protection', 'pregnant'),
    (r'\b(maternity)\b', 'maternity leave maternity protection act benefit', 'maternity'),
    (r'\b(paternity|new father|new dad)\b', 'paternity leave paternity leave and benefit act', 'paternity'),
    (r"\b(parent'?s?\s*leave)\b", 'parents leave and benefit act parental leave', 'parents-leave'),
    (r'\b(carer|caring for someone)\b', 'carers leave carer leave act', 'carer'),
    (r'\b(adoption|adopted)\b', 'adoptive leave adoptive leave act', 'adoption'),
    (r'\b(bereavement|death in family|funeral)\b', 'compassionate leave bereavement', 'bereavement'),
    (r'\b(force majeure)\b', 'force majeure leave urgent family reasons', 'force-majeure'),
    (r'\b(public holiday)\b', 'public holiday entitlement organisation of working time', 'public-holiday'),

    # --- Bullying & Harassment ---
    (r'\b(bull(?:y|ied|ying)|being bullied)\b', 'bullying dignity at work code of practice', 'bullied'),
    (r'\b(harassed|harassment)\b', 'harassment employment equality code of practice', 'harassment'),
    (r'\b(hostile|toxic|bad atmosphere)\b', 'bullying harassment dignity at work', 'toxic'),
    (r'\b(picked on|singled out|on my case)\b', 'bullying victimisation dignity at work', 'picked-on'),
    (r'\b(giving me grief|constant hassle|treated badly)\b', 'bullying harassment dignity at work', 'giving-grief'),
    (r'\b(sexual harassment)\b', 'sexual harassment employment equality act', 'sexual-harassment'),

    # --- Discrimination ---
    (r'\b(discriminat\w+)\b', 'discrimination employment equality act nine grounds', 'discrimination'),
    (r'\b(treated differently|treated unfairly)\b', 'discrimination equal treatment employment equality', 'treated-differently'),
    (r'\b(because of my age)\b', 'age discrimination employment equality act', 'age-discrimination'),
    (r"\b(because i'?m (pregnant|a woman|female|male))\b", 'gender discrimination employment equality act', 'gender-discrimination'),
    (r"\b(because of my race|because i'?m (foreign|immigrant|migrant))\b", 'race discrimination employment equality act', 'race-discrimination'),
    (r'\b(because of my disability)\b', 'disability discrimination reasonable accommodation employment equality', 'disability-discrimination'),
    (r'\b(because of my religion)\b', 'religion discrimination employment equality act', 'religion-discrimination'),
    (r'\b(traveller)\b', 'traveller community membership discrimination employment equality', 'traveller'),
    (r'\b(equal pay)\b', 'equal pay equal remuneration employment equality act', 'equal-pay'),
    # Protected grounds - disclosure / interview questions
    (r'\b(marital status|married|single|divorced|separated)\b', 'marital status discrimination employment equality act nine grounds', 'marital-status'),
    (r'\b(sexual orientation|gay|lesbian|bisexual|lgbt)\b', 'sexual orientation discrimination employment equality act', 'sexual-orientation'),
    (r'\b(family status|children|childcare|dependants)\b', 'family status discrimination employment equality act', 'family-status'),
    (r'\b(disclose|have to tell|obliged to tell|ask me about)\b', 'discrimination employment equality protected grounds employer questions', 'disclose'),

    # --- Contracts & Employment Status ---
    (r'\b(no contract|without a contract|no paperwork|no terms)\b', 'terms of employment written statement contract', 'no-contract'),
    (r'\b(changed? my contract)\b', 'change of terms of employment unilateral variation', 'changed-contract'),
    (r'\b(probation)\b', 'probationary period unfair dismissals terms of employment', 'probation'),
    (r'\b(bogus self[- ]?employ\w*)\b', 'bogus self employment understanding employment status contract of service determining employment', 'bogus-se'),
    (r'\b(am i self[- ]?employed|self[- ]?employed or not|am i an employee)\b', 'understanding employment status contract of service determining employment employee self-employed', 'employment-status'),

    # --- Redundancy ---
    (r'\b(made redundant|redundancy)\b', 'redundancy payments act genuine redundancy lump sum', 'redundancy'),
    (r'\b(laid off|layoff|lay[- ]?off)\b', 'redundancy lay-off short time working', 'laid-off'),
    (r'\b(stood down|sent home)\b', 'lay-off short time working suspension', 'stood-down'),
    (r'\b(closing down|company closing)\b', 'redundancy collective redundancy insolvency', 'closing-down'),

    # --- Safety ---
    (r'\b(unsafe|not safe|site unsafe)\b', 'health and safety welfare at work safety statement', 'unsafe'),
    (r'\b(dangerous work|dangerous conditions)\b', 'safety health welfare at work act risk assessment', 'dangerous'),
    (r'\b(accident at work|injured at work)\b', 'workplace accident health and safety authority', 'accident'),
    (r'\b(no training)\b', 'safety training health and safety welfare at work', 'no-training'),
    (r'\b(no gear|no ppe)\b', 'personal protective equipment health and safety', 'no-ppe'),
    (r'\b(no safety cert)\b', 'safety training certification health and safety', 'no-safety-cert'),

    # --- Whistleblowing ---
    (r'\b(report my employer|report wrongdoing)\b', 'protected disclosures whistleblower', 'report-employer'),
    (r'\b(whistleblow\w*)\b', 'protected disclosures act whistleblower protection', 'whistleblower'),
    (r'\b(speak up|raise concerns?)\b', 'protected disclosure raise concern grievance', 'speak-up'),

    # --- Complaints & Process ---
    (r'\b(make a complaint|lodge a complaint|complain)\b', 'workplace relations commission complaint adjudication', 'complaint'),
    (r'\b(take them to court|sue my employer)\b', 'workplace relations commission complaint labour court', 'sue'),
    (r'\b(time limit|deadline|how long do i have)\b', 'six month time limit complaint workplace relations commission', 'time-limit'),

    # --- Unions ---
    (r'\b(join a union|get a union)\b', 'trade union membership right to organise', 'join-union'),
    (r'\b(union rep|shop steward)\b', 'trade union representative collective bargaining', 'union-rep'),

    # --- Surveillance / Data Protection ---
    (r'\b(record|recording|recorded|monitor|monitoring|surveillance|cctv|camera|tracking|spying)\b', 'surveillance monitoring data protection privacy workplace gdpr', 'surveillance'),

    # --- Flexible / Remote Work ---
    (r'\b(work from home|wfh|remote work)\b', 'flexible working remote working right to request code of practice', 'remote'),
    (r'\b(flexible hours|flexible working)\b', 'flexible working right to request work life balance act', 'flexible'),

    # --- Agency / Temp / Part-time / Gig ---
    (r'\b(agency worker|through an agency|temp agency)\b', 'temporary agency work equal treatment', 'agency'),
    (r'\b(part[- ]?time)\b', 'part-time work protection of employees equal treatment', 'part-time'),
    (r'\b(fixed[- ]?term|temporary contract)\b', 'fixed-term work protection four year rule permanent', 'fixed-term'),
    (r'\b(gig work|gig economy|deliveroo|just eat|uber)\b', 'platform work employment status bogus self-employment', 'gig'),
]

# Compile all conversational patterns at module load
CONVERSATIONAL_EXPANSIONS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(pattern, re.IGNORECASE), terms, label)
    for pattern, terms, label in _CONVERSATIONAL_RAW
]

# Maximum appended terms to prevent query bloat / dilution
MAX_APPENDED_TOKENS = 25


def preprocess_query(query: str) -> Tuple[str, dict]:
    """
    Preprocess a user query for better retrieval.

    Applies abbreviation expansions and conversational-to-legal term mapping.
    Expansions are APPENDED to the query so both the original conversational
    language and the legal terms contribute to the embedding.

    Returns:
        Tuple of (enhanced_query, metadata_dict)
    """
    original = query
    enhanced = query
    expansions_used = []

    # Step 1: Abbreviation expansions (replace in-place)
    for compiled_rx, replacement, label in ABBREVIATION_EXPANSIONS:
        if compiled_rx.search(enhanced):
            enhanced = compiled_rx.sub(replacement, enhanced)
            expansions_used.append(f"abbrev:{label}")

    # Step 2: Conversational expansions (append legal terms)
    appended_terms = []
    for compiled_rx, legal_terms, label in CONVERSATIONAL_EXPANSIONS:
        if compiled_rx.search(enhanced):
            appended_terms.append(legal_terms)
            expansions_used.append(f"legal:{label}")

    if appended_terms:
        # Deduplicate terms while preserving order
        seen = set()
        unique_terms = []
        for term_group in appended_terms:
            for term in term_group.split():
                lower_term = term.lower()
                if lower_term not in seen:
                    seen.add(lower_term)
                    unique_terms.append(term)

        # Cap appended tokens to prevent query dilution
        unique_terms = unique_terms[:MAX_APPENDED_TOKENS]
        enhanced = f"{enhanced} {' '.join(unique_terms)}"

    metadata = {
        "original_query": original,
        "enhanced_query": enhanced,
        "expansions_used": expansions_used,
        "was_expanded": enhanced != original,
    }

    return enhanced, metadata
