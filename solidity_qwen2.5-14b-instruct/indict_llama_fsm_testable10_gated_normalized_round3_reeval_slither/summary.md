# Solidity Result Summary

- Generated at: 2026-04-17T16:55:21
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
- Slither findings total: 5
- Slither command available / passed / unavailable: 9 / 9 / 0
- Slither blocking/review/spec-conflict/quality/acceptable: 0/0/2/2/1
- Gas available / average: 6 / 782610.7
- LLM calls total / avg per sample: 0 / 0.0
- LLM call split actor/critic/tool-planning: 0/0/0
- Prompt/completion chars: 0 / 0
- Final status: compile_failed=1, passed_clean=2, passed_with_extra_abi=1, passed_with_slither_findings=3, test_failed=3

| idx | dataset_id | contract | partition | compile | ABI | test | abi_extra | slither classes | gas | llm calls | status | guard/stop | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True |  | B0/R0/S0/Q1/A0 | 944108 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | True | True | True |  | B0/R0/S0/Q0/A0 | 460815 | 0 | passed_clean | initial_action_passed_clean |  |
| 2 | 2 | TeamVestingVault | main | True | True | False |  | B0/R0/S0/Q0/A1 | None | 0 | test_failed |  | testInvestorWithdrawsAfterUnlock: Insufficient balance |
| 3 | 3 | TokenVoting | diagnostic | True | True | False |  | B0/R0/S0/Q0/A0 | None | 0 | test_failed |  | testOwnerAddsCandidates: assertion failed: Bob != Alice |
| 4 | 4 | PostingBoard | diagnostic | True | True | True |  | B0/R0/S0/Q1/A0 | 1004524 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 5 | 5 | CollectibleSale | main | True | True | True |  | B0/R0/S0/Q0/A0 | 758876 | 0 | passed_clean | initial_action_passed_clean |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True | fallback() | B0/R0/S0/Q0/A0 | 899231 | 0 | passed_with_extra_abi | reverted_to_initial_action_after_first_rewrite_regression |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | True |  | B0/R0/S1/Q0/A0 | 628110 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 8 | 8 | GrandGooseMansion | main | False | None | None |  | B0/R0/S0/Q0/A0 | None | 0 | compile_failed |  | Error (6160): Wrong argument count for function call: 0 arguments given but expected 4. |
| 9 | 9 | ClosedPresaleMint | main | True | True | False |  | B0/R0/S1/Q0/A0 | None | 0 | test_failed |  | testPublicMint: Public sale cannot be started yet |
