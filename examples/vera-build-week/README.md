# Vera Build Week synthetic example

This folder contains synthetic data for the electronic-invoice evidence flow
added to Vera during OpenAI Build Week 2026. It contains no customer data.

- `journal.csv` has two sampled entries.
- `invoice_INV-42.xml` is a minimal synthetic Italian FatturaPA document.

Run the commands in the root [README](../../README.md#reproduce-the-synthetic-build-week-flow).
The expected review has one unique supported entry and one unresolved entry.
The unresolved row demonstrates that Vera requests targeted evidence instead
of guessing.
