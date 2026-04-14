# Solidity Result Summary

- Generated at: 2026-04-14T14:58:14
- Total samples: 10
- Results present: 10
- Compile success: 5
- Compile failed: 5
- ABI checked: 5
- ABI passed: 5
- ABI failed: 0
- Tests passed: 4
- Tests failed: 1
- Rollback triggered: 0
- Final status: compile_failed=5, passed_clean=1, passed_with_extra_abi=1, passed_with_slither_findings=2, test_failed=1

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | status | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 0 | 777255 | passed_clean |  |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 2 | 2 | TeamVestingVault | main | True | True | True | 1 | 580569 | passed_with_slither_findings |  |  |
| 3 | 3 | TokenVoting | diagnostic | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 4 | 4 | PostingBoard | diagnostic | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 5 | 5 | CollectibleSale | main | True | True | True | 0 | 775161 | passed_with_extra_abi |  |  |
| 6 | 6 | FundPoolManager | diagnostic | False | None | None | None | None | compile_failed |  | Error (9582): Member "pools" not found or not visible after argument-dependent lookup in contract FundPoolManager. |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 1 | 651311 | passed_with_slither_findings |  |  |
| 8 | 8 | GrandGooseMansion | main | False | None | None | None | None | compile_failed |  | Error (6160): Wrong argument count for function call: 1 arguments given but expected 0. |
| 9 | 9 | ClosedPresaleMint | main | True | True | False | 1 | None | test_failed |  | Public sale cannot start yet |
