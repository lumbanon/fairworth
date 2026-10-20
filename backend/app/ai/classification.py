"""One category/uncertainty contract for prompts, schemas and evidence checks."""

ALLOWED_UNCERTAINTIES = {
    "reported_fact": ("documented", "limited"),
    "historical_metric": ("documented", "analytical", "limited"),
    "valuation_output": ("analytical", "limited"),
    "policy_estimate": ("analytical", "limited"),
    "user_assumption": ("analytical", "limited"),
    "filing_excerpt": ("documented", "limited"),
    "company_profile": ("documented", "limited"),
    "interpretation": ("analytical", "limited"),
    "unavailable": ("unavailable",),
}

CLASSIFICATION_INSTRUCTIONS = "Valid category / uncertainty combinations (no other pairs):\n" + "\n".join(
    f"- {category}: {' or '.join(uncertainties)}"
    for category, uncertainties in ALLOWED_UNCERTAINTIES.items()
)


def valid_classification(category, uncertainty):
    return uncertainty in ALLOWED_UNCERTAINTIES.get(category, ())
