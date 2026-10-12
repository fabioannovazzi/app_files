# Cowork business-planning skill integrity

Vera 0.1.360 and Clara 0.1.263 quote the existing colon-bearing business-planning description as a valid YAML scalar. The description and workflow are unchanged. Package inventories and SHA-256 checks remain strict.

The installed Cowork Vera 0.1.359 tree on Fabio's Mac reproduced Nicola's reported failure: `Installation content mismatch: skills/business-planning/SKILL.md`. Its file SHA-256 was `07ac30730790fec230e74f0fc9a24541abf87b83e2bab2777d168e0cfe0f1295`, while the released ZIP/index expected `3cb771ec90e9a334aef66c80dac7f43c4cb87bf940b38bba50b11db023836c0f`. A complete diff found exactly one change: quotation marks added around the YAML description. A complete indexed-file audit found this was the only mismatch. The unquoted source fails ordinary YAML parsing because its description includes `company: assess customers`.

Regression coverage reproduces the observed installer quotation before running the unchanged real component validator, and checks both entry-product descriptions through Cowork projection. Source, Codex and Cowork registration-PDF acceptance remains independently exercised. No generated installation is manually repaired. Nicola's original PDF acceptance remains outstanding.

The two business-planning courses are completely equal to the reviewed baseline except their source fingerprints. Existing teaching content, inputs, checkpoints, execution contracts, editorial judgments and historical artifact evidence are retained. No new model-context or external-data boundary is added. OpenAI Marketplace and its published-version notification manifest are unchanged.
