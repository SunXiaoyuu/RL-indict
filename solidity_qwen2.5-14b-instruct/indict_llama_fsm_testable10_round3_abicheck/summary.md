# Solidity Result Summary

- Generated at: 2026-04-13T19:26:16
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
- Final status: compile_failed=4, passed_clean=1, passed_with_slither_findings=4, test_failed=1

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | status | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 1 | 837151 | passed_with_slither_findings |  |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 2 | 2 | TeamVestingVault | main | True | True | True | 2 | 687716 | passed_with_slither_findings | reverted_to_mid_action_after_final_compile_failure |  |
| 3 | 3 | TokenVoting | diagnostic | True | True | False | 0 | None | test_failed |  | assertion failed: 0 != 1 |
| 4 | 4 | PostingBoard | diagnostic | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 5 | 5 | CollectibleSale | main | True | True | True | 0 | 905116 | passed_clean |  |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | 4 | 1130113 | passed_with_slither_findings |  |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 1 | 661414 | passed_with_slither_findings |  |  |
| 8 | 8 | GrandGooseMansion | main | False | None | None | None | None | compile_failed |  | Error (8936): Expected string end-quote. |
| 9 | 9 | ClosedPresaleMint | main | False | None | None | None | None | compile_failed |  | Error (2271): Built-in binary operator + cannot be applied to types uint256 and int_const -1. |

## Round Comparison

Rounds: round1 -> round2 -> round3

| idx | contract | compile | ABI | test | slither | gas | final status | final failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | MembershipAirdrop | T -> T -> T | T -> T -> T | T -> T -> T | 2 -> 2 -> 1 | 1157673 -> 1157937 -> 837151 | passed_with_slither_findings |  |
| 1 | SimpleCrowdsale | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (2333): Identifier already declared. |
| 2 | TeamVestingVault | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 2 | 643440 -> 643428 -> 687716 | passed_with_slither_findings |  |
| 3 | TokenVoting | F -> T -> T | - -> F -> T | - -> F -> F | - -> 0 -> 0 | - -> - -> - | test_failed | assertion failed: 0 != 1 |
| 4 | PostingBoard | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (2333): Identifier already declared. |
| 5 | CollectibleSale | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 905116 -> 905116 -> 905116 | passed_clean |  |
| 6 | FundPoolManager | T -> T -> T | T -> T -> T | T -> T -> T | 4 -> 4 -> 4 | 1007319 -> 1076260 -> 1130113 | passed_with_slither_findings |  |
| 7 | PresaleMint | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 660958 -> 661414 -> 661414 | passed_with_slither_findings |  |
| 8 | GrandGooseMansion | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (8936): Expected string end-quote. |
| 9 | ClosedPresaleMint | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (2271): Built-in binary operator + cannot be applied to types uint256 and int_const -1. |
