"""nitrd-classifier: inference MCP server that suggests NITRD categorization.

Task 1 (parent): TF-IDF + logistic regression on public category-329 labels.
Task 2 (subcategory): rule-based scope-vocabulary engine (abstains when the
evidence is thin). Suggestions only; nothing is written. Results demonstrate the
mechanism and are not validated accuracy claims.
"""

__version__ = "0.1.0"
