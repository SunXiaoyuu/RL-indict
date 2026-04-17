# Solidity Result Summary

- Generated at: 2026-04-17T17:25:51
- Total samples: 10
- Results present: 10
- Compile success: 10
- Compile failed: 0
- ABI checked: 10
- ABI passed: 10
- ABI failed: 0
- Tests passed: 7
- Tests failed: 3
- Rollback triggered: 0
- ABI extra samples: 0
- Slither findings total: 10
- Slither command available / passed / unavailable: 10 / 10 / 0
- Slither blocking/review/spec-conflict/quality/acceptable: 0/0/3/6/1
- Gas available / average: 7 / 861207.3
- LLM calls total / avg per sample: 18 / 1.8
- LLM call split actor/critic/tool-planning: 6/12/0
- Prompt/completion chars: 320733 / 49719
- Final status: passed_clean=1, passed_with_slither_findings=6, test_failed=3

| idx | dataset_id | contract | partition | compile | ABI | test | abi_extra | slither classes | gas | llm calls | status | guard/stop | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | MembershipAirdrop | main | True | True | True |  | B0/R0/S0/Q1/A0 | 894686 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 1 | 1 | SimpleCrowdsale | diagnostic | True | True | True |  | B0/R0/S0/Q0/A0 | 460149 | 0 | passed_clean | initial_action_passed_clean |  |
| 2 | 2 | TeamVestingVault | main | True | True | False |  | B0/R0/S0/Q0/A1 | None | 6 | test_failed |  | testInvestorWithdrawsAfterUnlock: EvmError: Revert |
| 3 | 3 | TokenVoting | diagnostic | True | True | False |  | B0/R0/S0/Q0/A0 | None | 6 | test_failed |  | testOwnerAddsCandidates: assertion failed: Bob != Alice |
| 4 | 4 | PostingBoard | diagnostic | True | True | True |  | B0/R0/S0/Q1/A0 | 927798 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 5 | 5 | CollectibleSale | main | True | True | True |  | B0/R0/S0/Q1/A0 | 722390 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 6 | 6 | FundPoolManager | diagnostic | True | True | True |  | B0/R0/S0/Q2/A0 | 980597 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 7 | 7 | PresaleMint | diagnostic | True | True | False |  | B0/R0/S1/Q0/A0 | None | 6 | test_failed |  | testPublicBuyOnlyWhenSaleLive: assertion failed: 0 != 1 |
| 8 | 8 | GrandGooseMansion | main | True | True | True |  | B0/R0/S1/Q1/A0 | 1066667 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |
| 9 | 9 | ClosedPresaleMint | main | True | True | True |  | B0/R0/S1/Q0/A0 | 976164 | 0 | passed_with_slither_findings | initial_action_passed_clean |  |

## Round Comparison

Rounds: round1 -> round2 -> round3

| idx | contract | compile | ABI | test | slither | gas | llm calls | final status | final failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | MembershipAirdrop | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 894686 -> 894686 -> 894686 | 1 -> 0 -> 0 | passed_with_slither_findings |  |
| 1 | SimpleCrowdsale | T -> T -> T | T -> T -> T | T -> T -> T | 0 -> 0 -> 0 | 460149 -> 460149 -> 460149 | 4 -> 0 -> 0 | passed_clean |  |
| 2 | TeamVestingVault | T -> T -> T | T -> T -> T | F -> F -> F | 1 -> 1 -> 1 | - -> - -> - | 7 -> 6 -> 6 | test_failed | testInvestorWithdrawsAfterUnlock: EvmError: Revert |
| 3 | TokenVoting | T -> T -> T | T -> T -> T | F -> F -> F | 0 -> 0 -> 0 | - -> - -> - | 7 -> 6 -> 6 | test_failed | testOwnerAddsCandidates: assertion failed: Bob != Alice |
| 4 | PostingBoard | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 927798 -> 927798 -> 927798 | 1 -> 0 -> 0 | passed_with_slither_findings |  |
| 5 | CollectibleSale | T -> T -> T | T -> T -> T | T -> T -> T | 1 -> 1 -> 1 | 722390 -> 722390 -> 722390 | 1 -> 0 -> 0 | passed_with_slither_findings |  |
| 6 | FundPoolManager | T -> T -> T | T -> T -> T | T -> T -> T | 2 -> 2 -> 2 | 980597 -> 980597 -> 980597 | 1 -> 0 -> 0 | passed_with_slither_findings |  |
| 7 | PresaleMint | T -> T -> T | T -> T -> T | F -> F -> F | 1 -> 1 -> 1 | - -> - -> - | 7 -> 6 -> 6 | test_failed | testPublicBuyOnlyWhenSaleLive: assertion failed: 0 != 1 |
| 8 | GrandGooseMansion | T -> T -> T | F -> T -> T | F -> T -> T | 4 -> 2 -> 2 | - -> 1066667 -> 1066667 | 8 -> 4 -> 0 | passed_with_slither_findings |  |
| 9 | ClosedPresaleMint | T -> T -> T | T -> T -> T | F -> T -> T | 1 -> 1 -> 1 | - -> 976164 -> 976164 | 7 -> 3 -> 0 | passed_with_slither_findings |  |
