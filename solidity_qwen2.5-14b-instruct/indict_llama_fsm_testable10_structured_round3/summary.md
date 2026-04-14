# Solidity Result Summary

- Generated at: 2026-04-14T10:18:51
- Total samples: 10
- Results present: 10
- Compile success: 7
- Compile failed: 3
- ABI checked: 7
- ABI passed: 7
- ABI failed: 0
- Tests passed: 4
- Tests failed: 3
- Rollback triggered: 4
- Final status: compile_failed=3, passed_clean=3, passed_with_slither_findings=1, test_failed=3

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | status | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 0 | 875071 | passed_clean | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | True | True | True | 0 | 518037 | passed_clean | reverted_to_mid_action_after_final_regression;reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 2 | 2 | TeamVestingVault | main | True | True | True | 1 | 586841 | passed_with_slither_findings | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 3 | 3 | TokenVoting | diagnostic | True | True | False | 0 | None | test_failed |  | assertion failed: 0x28cac318a86c8a0a6a9156c2dba2c8c2363677ba0514ef616592d81557e679b6 != 0x416c696365000000000000000000000000000000000000000000000000000000 |
| 4 | 4 | PostingBoard | diagnostic | False | None | None | None | None | compile_failed |  | Error (9582): Member "authorBalances" not found or not visible after argument-dependent lookup in contract PostingBoard. |
| 5 | 5 | CollectibleSale | main | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 6 | 6 | FundPoolManager | diagnostic | False | None | None | None | None | compile_failed |  | Error (2333): Identifier already declared. |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 0 | 800649 | passed_clean | reverted_to_mid_action_after_final_regression |  |
| 8 | 8 | GrandGooseMansion | main | True | True | False | 0 | None | test_failed |  | Sale is not in presale |
| 9 | 9 | ClosedPresaleMint | main | True | True | False | 0 | None | test_failed |  | Only deployer can initialize |

## Round Comparison

Rounds: round1 -> round2 -> round3

| idx | contract | compile | ABI | test | slither | gas | final status | final failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | MembershipAirdrop | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 875071 -> 875071 -> 875071 | passed_clean |  |
| 1 | SimpleCrowdsale | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 518049 -> 518037 -> 518037 | passed_clean |  |
| 2 | TeamVestingVault | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 586841 -> 586841 -> 586841 | passed_with_slither_findings |  |
| 3 | TokenVoting | T -> T -> T | T -> T -> T | F -> F -> F | 0 -> 0 -> 0 | - -> - -> - | test_failed | assertion failed: 0x28cac318a86c8a0a6a9156c2dba2c8c2363677ba0514ef616592d81557e679b6 != 0x416c696365000000000000000000000000000000000000000000000000000000 |
| 4 | PostingBoard | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (9582): Member "authorBalances" not found or not visible after argument-dependent lookup in contract PostingBoard. |
| 5 | CollectibleSale | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (2333): Identifier already declared. |
| 6 | FundPoolManager | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | compile_failed | Error (2333): Identifier already declared. |
| 7 | PresaleMint | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 0 | 1244136 -> 859585 -> 800649 | passed_clean |  |
| 8 | GrandGooseMansion | F -> T -> T | - -> T -> T | - -> F -> F | - -> 0 -> 0 | - -> - -> - | test_failed | Sale is not in presale |
| 9 | ClosedPresaleMint | T -> T -> T | T -> T -> T | F -> F -> F | 1 -> 0 -> 0 | - -> - -> - | test_failed | Only deployer can initialize |
