# Synthetic golden-retrieval contract fixture

Everything in this directory exists only to test the Week 4 schema and
provider-free validator. The questions, facts, documents, and provenance are
deliberately synthetic test data. They are not KnowledgeDesk golden labels and
must never be copied into the Week 4 labeling worksheet.

The fixture uses `purpose: contract_test` and `origin: synthetic_test`. The
schema rejects those markers in a real `purpose: golden` dataset.
