"""
Irish Workers' Rights Chatbot - Configuration

Security patterns, official sources, and metadata.
"""

# Last updated date for the knowledge base
# Update this when you re-ingest documents
KNOWLEDGE_BASE_UPDATED = "2026-01-15"

# Official sources to include with every response
OFFICIAL_SOURCES = {
    "wrc": "https://www.workplacerelations.ie",
    "citizens_info": "https://www.citizensinformation.ie/en/employment/",
    "hsa": "https://www.hsa.ie",
    "labour_court": "https://www.labourcourt.ie",
}

# Obvious prompt injection patterns
# Not trying to catch everything - just the lazy copy-paste attacks
# Claude's training handles more sophisticated attempts
OBVIOUS_INJECTION_PATTERNS = [
    "ignore previous",
    "ignore your instructions",
    "ignore all instructions",
    "ignore the above",
    "disregard your",
    "disregard previous",
    "forget your instructions",
    "forget your prompt",
    "system prompt",
    "reveal your prompt",
    "show your prompt",
    "print your instructions",
    "you are now",
    "you're now",
    "act as if",
    "pretend you are",
    "pretend to be",
    "roleplay as",
    "jailbreak",
    "dan mode",
    "developer mode",
    "sudo mode",
]

# UI Disclaimer text
DISCLAIMER = (
    "This chatbot provides general information about Irish employment law. "
    "It is not a substitute for professional legal advice. For specific situations, "
    "please consult a solicitor, your trade union, or contact the Workplace Relations Commission."
)
