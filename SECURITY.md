# Security Policy

## Supported Version

Security fixes target the latest release on the `main` branch.

## Reporting A Vulnerability

Do not open a public issue for credentials, authorization bypasses, sensitive logging, unsafe policy activation, or dependency vulnerabilities.

Report privately through [GitHub Security Advisories](https://github.com/Isoldelu/software-engineering-agent/security/advisories/new). Include the affected endpoint/module, reproduction steps, impact, and a minimal proof of concept. Do not include real enterprise data, production credentials, or third-party personal data.

The maintainer will acknowledge a valid report, assess severity, and publish a fix or mitigation before public disclosure when practical.

## Project Boundary

This repository uses simulated software-asset data. API Keys, database URLs, Audit JSONL, Trajectory files, backups, and CI artifacts must remain outside Git history. See `.env.example` for placeholders only.
