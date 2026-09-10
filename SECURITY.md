# Security

Do not put sensitive process arguments or complete diagnostic dumps in public issues.
If you find a security vulnerability, use the repository's private vulnerability
reporting feature once the maintainer enables it on GitHub. Until a repository and
private reporting channel are configured, do not publish exploit details in an issue.

0.1.x is the initially maintained series. The tool makes local read-only queries,
never starts sudo, and never executes a target binary. The caller's PATH determines
which system tools are used; run it in a trusted environment. Command line data can
contain credentials and should be reviewed before sharing output.
