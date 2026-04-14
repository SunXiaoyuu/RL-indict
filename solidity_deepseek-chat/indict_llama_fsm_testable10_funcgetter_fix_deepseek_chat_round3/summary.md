# Solidity Result Summary

- Generated at: 2026-04-14T14:03:30
- Total samples: 10
- Results present: 10
- Compile success: 10
- Compile failed: 0
- ABI checked: 10
- ABI passed: 10
- ABI failed: 0
- Tests passed: 10
- Tests failed: 0
- Rollback triggered: 5
- Final status: passed_clean=5, passed_with_slither_findings=5

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | status | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True | 0 | 645869 | passed_clean |  |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | True | True | True | 0 | 459114 | passed_clean | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 2 | 2 | TeamVestingVault | main | True | True | True | 1 | 399843 | passed_with_slither_findings |  |  |
| 3 | 3 | TokenVoting | diagnostic | True | True | True | 0 | 1059427 | passed_clean | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 4 | 4 | PostingBoard | diagnostic | True | True | True | 0 | 951536 | passed_clean |  |  |
| 5 | 5 | CollectibleSale | main | True | True | True | 1 | 737905 | passed_with_slither_findings |  |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | 1 | 605367 | passed_with_slither_findings |  |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True | 0 | 596405 | passed_clean | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 8 | 8 | GrandGooseMansion | main | True | True | True | 2 | 851963 | passed_with_slither_findings | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |
| 9 | 9 | ClosedPresaleMint | main | True | True | True | 1 | 796931 | passed_with_slither_findings | reverted_to_initial_action_after_better_compile_test_abi_security_or_gas_outcome |  |

## Round Comparison

Rounds: round1 -> round2 -> round3

| idx | contract | compile | ABI | test | slither | gas | final status | final failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | MembershipAirdrop | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 645869 -> 645869 -> 645869 | passed_clean |  |
| 1 | SimpleCrowdsale | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 459126 -> 459114 -> 459114 | passed_clean |  |
| 2 | TeamVestingVault | T -> T -> T | T -> T -> T | T -> T -> T | 2 -> 1 -> 1 | 411809 -> 399843 -> 399843 | passed_with_slither_findings |  |
| 3 | TokenVoting | T -> T -> T | T -> T -> T | F -> T -> T | 0 -> 0 -> 0 | - -> 1059427 -> 1059427 | passed_clean |  |
| 4 | PostingBoard | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 951536 -> 951536 -> 951536 | passed_clean |  |
| 5 | CollectibleSale | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 771771 -> 771771 -> 737905 | passed_with_slither_findings |  |
| 6 | FundPoolManager | T -> T -> T | T -> T -> T | T -> T -> T | 2 -> 1 -> 1 | 583850 -> 605367 -> 605367 | passed_with_slither_findings |  |
| 7 | PresaleMint | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 596405 -> 596405 -> 596405 | passed_clean |  |
| 8 | GrandGooseMansion | T -> T -> T | T -> T -> T | T -> T -> T | 2 -> 2 -> 2 | 870298 -> 851963 -> 851963 | passed_with_slither_findings |  |
| 9 | ClosedPresaleMint | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 810508 -> 796931 -> 796931 | passed_with_slither_findings |  |
