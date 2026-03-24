#!/bin/bash

# 修改模型配置为Qwen
model=qwen2.5-14b-instruct
task=$1  

# 策略保持不变（因为agent.py已经适配Qwen）
strategy=indict_llama 

echo " Experiment Config: $task $model $strategy " 



# 设置输出路径
output_path=${task}_${model}

# 3轮迭代优化
for i in {1..3}
do
    echo "=== Generation round # $i ==="
    
    if [ $i -eq 1 ]; then
        # 第一轮：初始生成
        suffix=_round${i}
        echo "Starting initial generation with Qwen model..."
        
        python run.py --model $model \
            --task $task \
            --strategy $strategy \
            --suffix $suffix \
            --debug 
            
    else
        # 第2-3轮：基于前轮结果迭代优化
        prev_trial_path=${output_path}/${strategy}_round$(($i - 1))/
        suffix=_round${i}
        
        echo "Prior trial path: $prev_trial_path"
        echo "Starting iterative optimization round $i..."
        
        python run.py --model $model \
            --task $task \
            --strategy $strategy \
            --prev_trial $prev_trial_path \
            --suffix $suffix \
            --debug
    fi
    
    # 检查执行结果
    if [ $? -eq 0 ]; then
        echo "✓ Round $i completed successfully"
    else
        echo "✗ Round $i failed, please check the error logs"
        break
    fi
    
    echo "----------------------------------------"
done

echo "=== All 3 rounds completed ==="
echo "Final results saved in: $output_path"