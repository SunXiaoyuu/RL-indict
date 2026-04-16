# Solidity Result Summary

- Generated at: 2026-04-16T17:58:02
- Total samples: 10
- Results present: 10
- Compile success: 9
- Compile failed: 1
- ABI checked: 9
- ABI passed: 9
- ABI failed: 0
- Tests passed: 6
- Tests failed: 3
- Rollback triggered: 1
- ABI extra samples: 1
- Slither findings total: 0
- Slither blocking/review/spec-conflict/quality/acceptable: 0/0/0/0/0
- Gas available / average: 6 / 782610.7
- LLM calls total / avg per sample: 27 / 2.7
- LLM call split actor/critic/tool-planning: 9/18/0
- Prompt/completion chars: 447031 / 81866
- Final status: compile_failed=1, passed_clean=5, passed_with_extra_abi=1, test_failed=3

| idx | dataset_id | contract | partition | compile | ABI | test | abi_extra | slither classes | gas | llm calls | status | guard/stop | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True |  | B0/R0/S0/Q0/A0 | 944108 | 0 | passed_clean | initial_action_passed_clean |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | True | True | True |  | B0/R0/S0/Q0/A0 | 460815 | 0 | passed_clean | initial_action_passed_clean |  |
| 2 | 2 | TeamVestingVault | main | True | True | False |  | B0/R0/S0/Q0/A0 | None | 6 | test_failed |  | testInvestorWithdrawsAfterUnlock: Insufficient balance |
| 3 | 3 | TokenVoting | diagnostic | True | True | False |  | B0/R0/S0/Q0/A0 | None | 6 | test_failed |  | testOwnerAddsCandidates: assertion failed: Bob != Alice |
| 4 | 4 | PostingBoard | diagnostic | True | True | True |  | B0/R0/S0/Q0/A0 | 1004524 | 0 | passed_clean | initial_action_passed_clean |  |
| 5 | 5 | CollectibleSale | main | True | True | True |  | B0/R0/S0/Q0/A0 | 758876 | 0 | passed_clean | initial_action_passed_clean |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | fallback() | B0/R0/S0/Q0/A0 | 899231 | 3 | passed_with_extra_abi | reverted_to_initial_action_after_first_rewrite_regression |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True |  | B0/R0/S0/Q0/A0 | 628110 | 0 | passed_clean | initial_action_passed_clean |  |
| 8 | 8 | GrandGooseMansion | main | False | None | None |  | B0/R0/S0/Q0/A0 | None | 6 | compile_failed |  | Error (6160): Wrong argument count for function call: 0 arguments given but expected 4. |
| 9 | 9 | ClosedPresaleMint | main | True | True | False |  | B0/R0/S0/Q0/A0 | None | 6 | test_failed |  | testPublicMint: Public sale cannot be started yet |

## Round Comparison

Rounds: round1 -> round2 -> round3

| idx | contract | compile | ABI | test | slither | gas | llm calls | final status | final failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | MembershipAirdrop | T -> T -> T | T -> T -> T | T -> T -> T | - -> - -> - | 944108 -> 944108 -> 944108 | 1 -> 0 -> 0 | passed_clean |  |
| 1 | SimpleCrowdsale | T -> T -> T | T -> T -> T | T -> T -> T | - -> - -> - | 460815 -> 460815 -> 460815 | 4 -> 0 -> 0 | passed_clean |  |
| 2 | TeamVestingVault | T -> T -> T | T -> T -> T | F -> F -> F | - -> - -> - | - -> - -> - | 7 -> 6 -> 6 | test_failed | testInvestorWithdrawsAfterUnlock: Insufficient balance |
| 3 | TokenVoting | T -> T -> T | T -> T -> T | F -> F -> F | - -> - -> - | - -> - -> - | 7 -> 6 -> 6 | test_failed | testOwnerAddsCandidates: assertion failed: Bob != Alice |
| 4 | PostingBoard | T -> T -> T | T -> T -> T | T -> T -> T | - -> - -> - | 1004524 -> 1004524 -> 1004524 | 1 -> 0 -> 0 | passed_clean |  |
| 5 | CollectibleSale | T -> T -> T | T -> T -> T | T -> T -> T | - -> - -> - | 758876 -> 758876 -> 758876 | 1 -> 0 -> 0 | passed_clean |  |
| 6 | FundPoolManager | T -> T -> T | T -> T -> T | T -> T -> T | - -> - -> - | 899231 -> 899231 -> 899231 | 4 -> 3 -> 3 | passed_with_extra_abi |  |
| 7 | PresaleMint | T -> T -> T | T -> T -> T | T -> T -> T | - -> - -> - | 647105 -> 628110 -> 628110 | 7 -> 3 -> 0 | passed_clean |  |
| 8 | GrandGooseMansion | F -> F -> F | - -> - -> - | - -> - -> - | - -> - -> - | - -> - -> - | 7 -> 6 -> 6 | compile_failed | Error (6160): Wrong argument count for function call: 0 arguments given but expected 4. |
| 9 | ClosedPresaleMint | T -> T -> T | T -> T -> T | F -> F -> F | - -> - -> - | - -> - -> - | 7 -> 6 -> 6 | test_failed | testPublicMint: Public sale cannot be started yet |
