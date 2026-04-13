# Solidity Result Summary

- Generated at: 2026-04-13T23:36:31
- Total samples: 10
- Results present: 10
- Compile success: 10
- Compile failed: 0
- ABI checked: 10
- ABI passed: 10
- ABI failed: 0
- Tests passed: 6
- Tests failed: 4
- Rollback triggered: 6
- Final status: passed_clean=3, passed_with_slither_findings=3, test_failed=4

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | status | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 0 | 791401 | passed_clean |  |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | True | True | True | 0 | 595671 | passed_clean | reverted_to_initial_action_after_better_compile_or_test_outcome |  |
| 2 | 2 | TeamVestingVault | main | True | True | False | 2 | None | test_failed | reverted_to_initial_action_after_better_compile_or_test_outcome | EvmError: Revert |
| 3 | 3 | TokenVoting | diagnostic | True | True | False | 0 | None | test_failed | reverted_to_initial_action_after_better_compile_or_test_outcome | assertion failed: Bob != Alice |
| 4 | 4 | PostingBoard | diagnostic | True | True | True | 1 | 1145944 | passed_with_slither_findings | reverted_to_initial_action_after_better_compile_or_test_outcome |  |
| 5 | 5 | CollectibleSale | main | True | True | True | 0 | 791198 | passed_clean |  |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | 3 | 1073180 | passed_with_slither_findings |  |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 1 | 689847 | passed_with_slither_findings | reverted_to_mid_action_after_final_compile_failure |  |
| 8 | 8 | GrandGooseMansion | main | True | True | False | 2 | None | test_failed |  | Already started |
| 9 | 9 | ClosedPresaleMint | main | True | True | False | 1 | None | test_failed | reverted_to_mid_action_after_final_compile_failure | Public sale already started or presale not started |

## Round Comparison

Rounds: round1 -> round2 -> round3

| idx | contract | compile | ABI | test | slither | gas | final status | final failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | MembershipAirdrop | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 791401 -> 791401 -> 791401 | passed_clean |  |
| 1 | SimpleCrowdsale | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 595671 -> 595671 -> 595671 | passed_clean |  |
| 2 | TeamVestingVault | T -> T -> T | T -> T -> T | F -> F -> F | 2 -> 2 -> 2 | - -> - -> - | test_failed | EvmError: Revert |
| 3 | TokenVoting | T -> T -> T | T -> T -> T | F -> F -> F | 0 -> 0 -> 0 | - -> - -> - | test_failed | assertion failed: Bob != Alice |
| 4 | PostingBoard | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 1145944 -> 1145944 -> 1145944 | passed_with_slither_findings |  |
| 5 | CollectibleSale | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 783150 -> 791198 -> 791198 | passed_clean |  |
| 6 | FundPoolManager | T -> T -> T | T -> T -> T | T -> T -> T | 3 -> 3 -> 3 | 1073180 -> 1073180 -> 1073180 | passed_with_slither_findings |  |
| 7 | PresaleMint | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 632168 -> 632168 -> 689847 | passed_with_slither_findings |  |
| 8 | GrandGooseMansion | T -> T -> T | T -> T -> T | F -> F -> F | 2 -> 2 -> 2 | - -> - -> - | test_failed | Already started |
| 9 | ClosedPresaleMint | T -> T -> T | T -> T -> T | F -> F -> F | 1 -> 1 -> 1 | - -> - -> - | test_failed | Public sale already started or presale not started |
