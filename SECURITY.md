# Security policy

## Report a vulnerability

Use the repository's private security advisory flow. Do not open a public issue for a credential leak or a vulnerability that exposes private data.

## Repository boundary

Keep credentials, cookies, access tokens, personal filesystem paths, private memory, business records, research data, and runtime logs out of this repository. Tests and examples must use synthetic values.

The core does not execute model-provider calls or load user credentials. Adapters that add those capabilities need their own threat model and review.
