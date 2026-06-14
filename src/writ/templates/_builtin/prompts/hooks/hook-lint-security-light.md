## Security Quick Check (OWASP AST10)

Flag any: hardcoded secrets (API keys, tokens), shell injection (`eval`/`exec`/`curl|bash`), data exfiltration, over-privileged access (AST03), identity impersonation (AST04), encoded payloads/unsafe deserialization (AST05), or agent identity file writes (AST01). Report each as `[SECURITY/ASTxx]` with severity. Skip if none found.
