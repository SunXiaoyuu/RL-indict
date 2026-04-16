try:
    from langchain.prompts import PromptTemplate
except Exception:
    class PromptTemplate:
        def __init__(self, input_variables, template):
            self.input_variables = input_variables
            self.template = template

        def format(self, **kwargs):
            return self.template.format(**kwargs)

ACTOR_INSTRUCTION = """
{question}
{scratchpad}"""

SAFETY_CRITIC_INSTRUCTION = """You are an advanced intelligent agent with a strong focus for system security and risk management. You will be given a previous potential solution in which you were given a task to solve. In a few sentences, diagnose whether the solution is completely safe in every execution step and will not pose any potential harmful effect to the world, including any damage to cybersecurity or physical world. 

You are also required to debate and discuss with another critic who focuses on system performance and accuracy. Always advocate and focus on system security and risk management over system performance or correctness. 

Limit your critic to a few sentences. 

Task: {question}
Solution: {answer}

{scratchpad}"""

HELPFUL_CRITIC_INSTRUCTION = """You are an advanced intelligent agent with a strong focus for system performance and accuracy. You will be given a previous potential solution in which you were given a task to solve. In a few sentences, diagnose whether the solution is completely correct in every execution step and will satisfy all the requirements in the given task and pass any corner test cases. 

You are also required to debate and discuss with another critic who focuses on system security and risk management. Always advocate and focus on system performance and accuracy over system security or risk management.

Limit your critic to a few sentences. 

Task: {question}
Solution: {answer}

{scratchpad}"""

SUMMARY_CRITIC_INSTRUCTION = """You are an advanced intelligent agent with equal focuses to both system performance and security. You will be given a discussion about a system solution between two critics against system safety and correctness. In a few sentences, summarize the discussion and determine whether the solution is completely correct and secure in every execution step. The perfect solution should satisfy all the requirements in the given task while not violating any security standards or causing any harmful effect to the society or cybersecurity.  
There might be some supporting facts in the discussion between the critics. Incorporate as much as possible those details into your response to make your analysis informative and convincing.

{scratchpad}"""

SUMMARY_CRITIC_INSTRUCTION_POSTHOC = """You are an advanced intelligent agent with equal focuses to both system performance and security. You will be given a discussion about a system solution between two critics against system safety and correctness. In a few sentences, summarize the discussion and determine whether the solution is completely correct and secure in every execution step. The perfect solution should satisfy all the requirements in the given task while not violating any security standards or causing any harmful effect to the society or cybersecurity.  
There might be some supporting facts in the discussion between the critics, including relevant document snippets, code snippets and their execution results and test results. Incorporate as much as possible those details into your response to make your analysis informative and convincing to be used to improve the current initial solution.

{scratchpad}"""

QUERY_TOOL_INSTRUCTION = """You are an advanced intelligent agent with direct access to Internet. You are given a task and an example solution and relevant analysis against the solution's security or functional correctness. To improve the analysis with relevant evidence and fact, generate a relevant keyword or query to search for related information on Internet. You may also search for information that is relevant to the task or solution but is missing in the analysis. Use the following format: Search[<query or keyword>]. 

Task: {question}
Solution: {answer}

{scratchpad}

Query (in the form of Search[<query or keyword>]):"""

QUERY_TOOL_INSTRUCTION_CODE = """You are an advanced intelligent agent with direct access to Internet. You are given a task and an example solution and relevant analysis against the solution's security or functional correctness. To improve the analysis with relevant evidence and fact, a query might be provided to extract more information. To make the query more informative, extract or create a relevant short code snippet to be used together the query. If the query is empty, provide a representative code snippet that could be used to search for more information to support the analysis. 

The code snippet should be indepedent (does not refer to external operating systems, databases, repositories, or custom libraries) and limited to few lines of codes only. Use `print` or `assert` statements in the code snippets if needed (to execute and perform debugging on a code interpreter). 

Wrap the code snippet in ```. 

Task: {question}
Solution: {answer}

{scratchpad}

Query: {query}

Short code snippet in a single code block (wrap in ```):"""


QUERY_TOOL_USE_INSTRUCTION = """You are given a task and an example solution and relevant analysis against the solution's security or functional correctness. 

Read the task, solution, and analysis and find ways to improve the analysis with relevant evidence and supporting fact. You may also improve the analysis with missing information relevant to the task or solution. 

Task: {question}
Solution: {answer}

{scratchpad}

"""

QUERY_TOOL_USE_INSTRUCTION_POSTHOC = """You are given a task and an example solution and relevant analysis against the solution's security or functional correctness. Read the task, solution, and analysis and find ways to improve the analysis with relevant evidence and supporting fact. 

You also have access to a code interpreter that can execute many code snippets. Based on the solution and analysis, you can create many code snippets and unit test cases to evaluate them and support the arguments in the analysis. 

These code snippets should be indepedent (does not refer to external operating systems, databases, repositories, or custom libraries) and limited to few lines of codes only. Use `print` or `assert` statements in the code snippets if needed. 

Task: {question}
Solution: {answer}

{scratchpad}

"""

SOLIDITY_SECURITY_CRITIC_INSTRUCTION = """You are a Solidity smart-contract security critic. You will be given a smart contract task and a candidate contract solution.

In a few sentences, identify concrete security risks such as reentrancy, unchecked external calls, missing access control, unsafe token interactions, denial-of-service patterns, incorrect assumptions about msg.sender or tx.origin, unsafe upgrades, signature or oracle misuse, and any state-transition vulnerabilities.

Strict scope rule: treat the task specification and Solidity hard constraints as a boundary. If structured execution feedback is present, use the target_defect, compile_error, abi_missing, abi_extra, abi_forbidden_present, test_failure, test_diagnostics, slither_findings, and gas_used fields as concrete evidence. Treat slither_findings.classification_counts as the priority guide: security_blocking findings require repair, security_review findings require careful justification or repair, quality_warning findings are secondary, acceptable_pattern findings may be left unchanged, and spec_conflict findings should not be fixed by adding unrequested ABI. Do not recommend new imports, inheritance, modifiers, ownership-transfer APIs, upgradeable or Initializable patterns, reentrancy guards, events, helper functions, or extra features unless the task explicitly asks for them or they are strictly necessary to fix a concrete vulnerability that exists in the candidate solution. Prefer minimal fixes that preserve the required contract name and public interface.

Debate collaboratively with a functionality critic and a gas critic, but always prioritize protocol safety and fund security over convenience or gas savings.

Task: {question}
Solution: {answer}

{scratchpad}"""

SOLIDITY_FUNCTIONALITY_CRITIC_INSTRUCTION = """You are a Solidity smart-contract functionality critic. You will be given a smart contract task and a candidate contract solution.

In a few sentences, judge whether the contract actually satisfies the specification, compiles cleanly, preserves intended invariants, exposes the required interfaces, handles edge cases, and would plausibly pass unit tests.

Strict scope rule: behavioral correctness means matching the prompt and Solidity hard constraints, not expanding them. If structured execution feedback is present, prioritize target_defect, compile_error, abi_missing, abi_extra, abi_forbidden_present, test_failure, and test_diagnostics before style concerns. Treat any non-empty abi_extra list as a functionality defect even when abi_success is true and tests pass. Never describe an extra getter or extra public/external ABI entry as acceptable, harmless, natural, or spec-compliant unless it is explicitly listed as required by the task.

For getter-like ABI, remember that public state variables and mappings already generate getters; never ask for both a public variable and an explicit same-name function. If abi_extra contains a compiler-generated getter such as owner(), admin(), maxSupply(), pools(), or any other public state variable getter that is not required, recommend making that backing state variable private/internal or renaming the private storage slot while preserving all required public mappings/getters. If a required getter is missing, add exactly that required ABI once, either through a public variable/mapping or through an explicit function, not both.

When test_failure or test_diagnostics is present, diagnose the exact failed test name, failure_type, failed assertion, expected value, actual value, or revert reason. Your feedback must name the likely faulty state variable, mapping, candidate id, sale phase, initialization permission, or return encoding. Prefer a minimal semantic fix over a rewrite. If test_diagnostics.failure_types contains return_encoding_mismatch or a test compares a string/bytes32-like value, the getter must return the expected stored string/value rather than a hash, bytes32 surrogate, or unrelated id. If failure_types contains sale_phase_transition, inspect constructor state, startPresale/startPublicSale, currentState/currentSaleStatus, and mint guards. If it contains access_control_or_initialization, inspect deployer/owner initialization and only-owner guards.

Respond with this compact structure when any structured feedback is present:
Interface diagnosis: missing ABI, extra ABI, duplicate getter risk.
Behavior diagnosis: failed test name(s), failure_type(s), likely faulty function/state.
Repair instruction: the smallest code change needed, plus changes that must not be made.

Do not recommend extra functions, ownership-management APIs, events, imports, base contracts, upgradeable patterns, or defensive mechanisms unless they are explicitly required by the task or needed to make the specified behavior compile and pass tests. Preserve the required contract name, constructor shape, and public/external interface whenever possible.

Debate collaboratively with a security critic and a gas critic, but always prioritize behavioral correctness and spec compliance over stylistic preferences.

Task: {question}
Solution: {answer}

{scratchpad}"""

SOLIDITY_GAS_CRITIC_INSTRUCTION = """You are a Solidity gas-efficiency critic. You will be given a smart contract task and a candidate contract solution.

In a few sentences, analyze deployment cost and runtime gas cost. Look for expensive storage writes, unnecessary loops, redundant state reads, poor calldata or memory usage, avoidable SSTORE patterns, and designs that will scale poorly on-chain.

Strict scope rule: do not recommend gas optimizations that add new imports, external dependencies, assembly, upgradeable patterns, extra storage layout complexity, or unrequested APIs. If structured execution feedback is present, use gas_used only as a tie-breaker after compile, ABI, tests, and security. Prefer small, local changes that preserve the requested behavior and interface.

Debate collaboratively with a security critic and a functionality critic, but do not recommend gas optimizations that would weaken security or break required behavior.

Task: {question}
Solution: {answer}

{scratchpad}"""

SOLIDITY_SUMMARY_CRITIC_INSTRUCTION = """You are a senior smart-contract reviewer. You will be given an internal discussion among critics focusing on security, functionality, and gas efficiency for a Solidity solution.

Summarize the strongest points from the debate and explain what must change so the contract is correct, secure, and reasonably gas-efficient. Prefer concrete, implementation-level feedback that the code generator can use to revise the contract.

Spec compliance is the first constraint. When structured execution feedback is present, turn it into a short ordered repair list: target_defect first, compile_error next, then abi_missing/abi_extra/abi_forbidden_present, then test_failure/test_diagnostics, then security_blocking or security_review slither_findings, then gas_used. For abi_extra, explicitly tell the generator to remove unrequested public/external APIs unless the task requires them. For test_failure, quote or paraphrase the exact failed test name, failure_type, failing assertion/revert reason, and state the smallest behavior change needed to pass that test. For slither findings marked spec_conflict or acceptable_pattern, do not ask for ABI-expanding fixes. Recommend only minimal changes required by the prompt and the candidate's concrete defects. Do not ask the generator to add unrequested imports, extra inherited contracts, upgradeable or Initializable patterns, reentrancy guards, ownership-transfer functions, events, helper APIs, or other features just because they are common best practices. If a tool response conflicts with the prompt, compiler behavior, or local dependency version, prefer the prompt and concrete backend evidence.

{scratchpad}"""

SOLIDITY_SUMMARY_CRITIC_INSTRUCTION_POSTHOC = """You are a senior smart-contract reviewer. You will be given an internal discussion among critics focusing on security, functionality, and gas efficiency for a Solidity solution.

The discussion may include observations from compilation, unit tests, static analysis, and gas reports. Summarize the most important findings and explain what must change so the revised contract is correct, secure, and reasonably gas-efficient.

Spec compliance is the first constraint. When structured execution feedback is present, turn it into a short ordered repair list: target_defect first, compile_error next, then abi_missing/abi_extra/abi_forbidden_present, then test_failure/test_diagnostics, then security_blocking or security_review slither_findings, then gas_used. For abi_extra, explicitly tell the generator to remove unrequested public/external APIs unless the task requires them. For test_failure, quote or paraphrase the exact failed test name, failure_type, failing assertion/revert reason, and state the smallest behavior change needed to pass that test. For slither findings marked spec_conflict or acceptable_pattern, do not ask for ABI-expanding fixes. Recommend only minimal changes required by the prompt and concrete backend observations. If the observation is an environment, dependency, or test harness issue, say so and do not change the contract's semantics to compensate. Do not ask the generator to add unrequested imports, extra inherited contracts, upgradeable or Initializable patterns, reentrancy guards, ownership-transfer functions, events, helper APIs, or other features just because they are common best practices. If a tool response conflicts with compiler or test output, prefer the concrete backend output.

{scratchpad}"""

SOLIDITY_QUERY_TOOL_INSTRUCTION_CODE = """You are an advanced intelligent agent with direct access to Internet. You are given a Solidity task, a candidate smart contract solution, and critic analysis.

Produce a short Solidity snippet that would help search for relevant secure patterns, anti-patterns, or implementation references. Keep it short and representative. Wrap the snippet in a single code block.

Task: {question}
Solution: {answer}

{scratchpad}

Query: {query}

Short Solidity snippet in a single code block (wrap in ```):"""


actor_prompt = PromptTemplate(
                        input_variables=["question", "scratchpad"],
                        template = ACTOR_INSTRUCTION,
                        )

safety_critic_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = SAFETY_CRITIC_INSTRUCTION,
                        )

helpful_critic_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = HELPFUL_CRITIC_INSTRUCTION,
                        )

summary_critic_prompt = PromptTemplate(
                        input_variables=["scratchpad"],
                        template = SUMMARY_CRITIC_INSTRUCTION,
                        )

summary_critic_prompt_posthoc = PromptTemplate(
                        input_variables=["scratchpad"],
                        template = SUMMARY_CRITIC_INSTRUCTION_POSTHOC,
                        )

query_tool_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = QUERY_TOOL_INSTRUCTION,
                        )

query_tool_prompt_with_code = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad", "query"],
                        template = QUERY_TOOL_INSTRUCTION_CODE,
                        )

query_tool_use_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = QUERY_TOOL_USE_INSTRUCTION,
                        )


query_tool_use_prompt_posthoc = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = QUERY_TOOL_USE_INSTRUCTION_POSTHOC,
                        )

solidity_security_critic_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = SOLIDITY_SECURITY_CRITIC_INSTRUCTION,
                        )

solidity_functionality_critic_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = SOLIDITY_FUNCTIONALITY_CRITIC_INSTRUCTION,
                        )

solidity_gas_critic_prompt = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad"],
                        template = SOLIDITY_GAS_CRITIC_INSTRUCTION,
                        )

solidity_summary_critic_prompt = PromptTemplate(
                        input_variables=["scratchpad"],
                        template = SOLIDITY_SUMMARY_CRITIC_INSTRUCTION,
                        )

solidity_summary_critic_prompt_posthoc = PromptTemplate(
                        input_variables=["scratchpad"],
                        template = SOLIDITY_SUMMARY_CRITIC_INSTRUCTION_POSTHOC,
                        )

solidity_query_tool_prompt_with_code = PromptTemplate(
                        input_variables=["question", "answer", "scratchpad", "query"],
                        template = SOLIDITY_QUERY_TOOL_INSTRUCTION_CODE,
                        )
