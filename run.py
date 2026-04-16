import sys, os

import numpy as np
import json
import pdb 
from tqdm import tqdm 
import copy 

try:
    from transformers import AutoTokenizer
except Exception:
    AutoTokenizer = None

from configs import * 
from parse_arguments import *
from agents import AgentStrategy, Agents 
from util import load_data, get_model, get_code_before

args = parser.parse_args()
strategy: AgentStrategy = getattr(AgentStrategy, strategy_mapping[args.strategy])

# Set up output directory 
strategy_id = strategy.value  + args.suffix 
output_dir = '{}_{}'.format(args.task, args.model)
output_path = os.path.join(output_dir, strategy_id)
os.makedirs(output_path, exist_ok=True)

# Load data 
data, action_prompt_header, question_prompt_key = load_data(args.task, data_path=args.data_path)
    
# Set up tool 
search_tool = [tool_definitions['codesearch']]
search_tool_posthoc = [tool_definitions['codereview']]

# Set up tokenizer 
tokenizer = None 
if args.model == 'commandr' and AutoTokenizer is not None: 
    tokenizer = AutoTokenizer.from_pretrained(model_mapping[args.model])
    
# Set up agent
model = get_model(args.model, model_mapping, provider=args.provider)
agent_config = copy.deepcopy(agent_configs[strategy.value])
task_config = task_agent_configs.get(args.task, {}).get(strategy.value, {})
agent_config.update(task_config)

cost_profiles = {
    "full": {
        "critic_mode": "full",
        "feedback_mode": "full",
        "posthoc_policy": "always",
        "critic_tools_enabled": True,
        "early_stop": False,
    },
    "gated": {
        "critic_mode": "gated",
        "feedback_mode": "compact",
        "posthoc_policy": "failures",
        "critic_tools_enabled": False,
        "early_stop": True,
    },
    "cheap": {
        "critic_mode": "cheap",
        "feedback_mode": "compact",
        "posthoc_policy": "failures",
        "critic_tools_enabled": False,
        "early_stop": True,
    },
}
runtime_config = cost_profiles[args.cost_profile]

all_agents = [Agents(idx, 
               item[question_prompt_key],
               
               system_prompt=item['test_case_prompt'] if args.task=='promptinject' else None, 
               actor_prompt=agent_config['actor_prompt'], 
               
               safety_critic_prompt=agent_config.get('safety_critic_prompt', None),
               helpful_critic_prompt=agent_config.get('helpful_critic_prompt', None),
               gas_critic_prompt=agent_config.get('gas_critic_prompt', None),
               summary_critic_prompt=agent_config.get('summary_critic_prompt', None), 
               summary_critic_prompt_posthoc=agent_config.get('summary_critic_prompt_posthoc', None),
               
               tool_prompt=agent_config.get('tool_prompt', None), 
               tool_prompt_posthoc=agent_config.get('tool_prompt_posthoc', None), 
               tool_prompt_code=agent_config.get('tool_prompt_code', None), 
                
               action_llm=model, 
               critic_llm=model,
               critic_tool=search_tool, 
               critic_tool_posthoc=search_tool_posthoc, 
               action_prompt_header=action_prompt_header,
                     
               task = args.task,
               tokenizer=tokenizer,
               programming_language=item.get('language', item.get('lang', None)),
               code_before = get_code_before(item),
               sample_metadata=item,
               prev_trial=args.prev_trial + '/{}.json'.format(idx) if args.prev_trial else None, 
               cost_profile=args.cost_profile,
               critic_mode=runtime_config["critic_mode"],
               feedback_mode=runtime_config["feedback_mode"],
               posthoc_policy=runtime_config["posthoc_policy"],
               critic_tools_enabled=runtime_config["critic_tools_enabled"],
               early_stop=runtime_config["early_stop"],
               solidity_prompt_mode=args.solidity_prompt_mode,
                     
               ) for idx, item in enumerate(data)] 

    
# Run agents
count = 0 
for sample_idx, agents in tqdm(enumerate(all_agents), total=len(all_agents)):
    if os.path.exists(output_path + f'/{agents.sample_idx}.json') and not args.override:
        continue 

    if args.prev_trial is not None and agents.prev_trial is None: 
        print("Skip sample {} due to nonexisting prev_trial".format(sample_idx))
        continue 
        
    #if agents.programming_language != 'python': continue 

    result = agents.run(strategy = strategy)

    sample_idx = result['sample_idx']

    if (sample_idx % 50) == 0: 
        print('Current output path: ', output_path)

    json.dump(result, open(os.path.join(output_path, f'{sample_idx}.json'), 'w'), indent=4)

    count += 1 

    if args.debug: 
        break 
