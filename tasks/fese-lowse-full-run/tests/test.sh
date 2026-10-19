#!/bin/bash
mkdir -p /logs/verifier
python3 -I /tests/verify.py --audit-url http://replay:8080/audit --token-file /tests/verifier_token \
  --report /app/report.json --targets /tests/targets.json --out /logs/verifier
