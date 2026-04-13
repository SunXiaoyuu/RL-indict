# Solidity Result Summary

- Generated at: 2026-04-13T16:45:25
- Total samples: 10
- Results present: 10
- Compile success: 6
- Compile failed: 4
- ABI checked: 6
- ABI passed: 6
- ABI failed: 0
- Tests passed: 5
- Tests failed: 1
- Rollback triggered: 1

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 1 | 837151 |  |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | False | None | None | None | None |  | Error (2333): Identifier already declared. |
| 2 | 2 | TeamVestingVault | main | True | True | True | 2 | 687716 | reverted_to_mid_action_after_final_compile_failure |  |
| 3 | 3 | TokenVoting | diagnostic | True | True | False | 0 | None |  | assertion failed: 0 != 1 |
| 4 | 4 | PostingBoard | diagnostic | False | None | None | None | None |  | Error (2333): Identifier already declared. |
| 5 | 5 | CollectibleSale | main | True | True | True | 0 | 905116 |  |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | 4 | 1130113 |  |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 1 | 661414 |  |  |
| 8 | 8 | GrandGooseMansion | main | False | None | None | None | None |  | Error (8936): Expected string end-quote. |
| 9 | 9 | ClosedPresaleMint | main | False | None | None | None | None |  | Error (2271): Built-in binary operator + cannot be applied to types uint256 and int_const -1. |
