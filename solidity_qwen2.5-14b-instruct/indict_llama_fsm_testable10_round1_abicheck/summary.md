# Solidity Result Summary

- Generated at: 2026-04-13T14:32:26
- Total samples: 10
- Results present: 10
- Compile success: 5
- Compile failed: 5
- ABI checked: 5
- ABI passed: 5
- ABI failed: 0
- Tests passed: 5
- Tests failed: 0
- Rollback triggered: 0

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 2 | 1157673 |  |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | False | None | None | None | None |  | Error (2333): Identifier already declared. |
| 2 | 2 | TeamVestingVault | main | True | True | True | 1 | 643440 |  |  |
| 3 | 3 | TokenVoting | diagnostic | False | None | None | None | None |  | Error (9582): Member "candidateCount" not found or not visible after argument-dependent lookup in contract TokenVoting. |
| 4 | 4 | PostingBoard | diagnostic | False | None | None | None | None |  | Error (2333): Identifier already declared. |
| 5 | 5 | CollectibleSale | main | True | True | True | 0 | 905116 |  |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | 4 | 1007319 |  |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 1 | 660958 |  |  |
| 8 | 8 | GrandGooseMansion | main | False | None | None | None | None |  | Error (6160): Wrong argument count for function call: 0 arguments given but expected 1. |
| 9 | 9 | ClosedPresaleMint | main | False | None | None | None | None |  | Error (6275): Source "lib/openzeppelin-contracts/contracts/security/ReentrancyGuard.sol" not found: File not found. Searched the following locations: "/tmp/indict_solidity_9_4hy... |
