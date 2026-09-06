# OMAR persistence marker

Durable OMAR state belongs under the canonical backend data root:

`backend/data/superstructure/omar/`

The runtime resolves this location through `canonical_data_dir()`. The SQLite settlement ledger remains authoritative; OMAR policy files are derived learning checkpoints and audit/learning event streams.
