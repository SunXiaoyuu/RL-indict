# Solidity Result Summary

- Generated at: 2026-04-12T19:07:47
- Total samples: 5
- Results present: 5
- Compile success: 3
- Compile failed: 2
- ABI checked: 0
- ABI passed: 0
- ABI failed: 0
- Tests passed: 2
- Tests failed: 1
- Rollback triggered: 2

| idx | dataset_id | contract | partition | compile | ABI | test | vulns | gas | guard | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1 | SimpleCrowdsale | diagnostic | True | None | False | 1 | None |  | assertion failed: 10 != 10000000000000000000 |
| 1 | 3 | TokenVoting | diagnostic | False | None | None | None | None |  | Error (9582): Member "candidateCount" not found or not visible after argument-dependent lookup in contract TokenVoting. |
| 2 | 4 | PostingBoard | diagnostic | True | None | True | 1 | 996247 | reverted_to_initial_action_after_better_compile_or_test_outcome |  |
| 3 | 6 | FundPoolManager | diagnostic | False | None | None | None | None |  | Error (9582): Member "pools" not found or not visible after argument-dependent lookup in contract FundPoolManager. |
| 4 | 7 | PresaleMint | diagnostic | True | None | True | 1 | 635787 | reverted_to_initial_action_after_better_compile_or_test_outcome |  |
