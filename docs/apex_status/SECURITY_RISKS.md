# Current security risk register

See SECURITY_FINDINGS.md for reproduced findings and remaining trust boundaries;
SECURITY_AND_ROLLBACK.md for existing local controls. The five archive runtime
defects are contained by rejecting imports. Critical release blockers remain:
owner authentication, encrypted private storage, network destination enforcement,
global stop/revocation, independent audit protection and actual integration tests.
No current test authorizes production or private data processing.
