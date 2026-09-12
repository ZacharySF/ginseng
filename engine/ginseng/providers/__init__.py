"""Financial data provider adapters.

Every provider — CSV import, manual entry, or an institution API like
Nessie — normalizes into the same provider-neutral records so the rest
of the app never learns which source produced the data. Provider
secrets are engine-side environment variables only; they must never
reach the static web bundle.
"""
