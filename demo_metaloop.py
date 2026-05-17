#!/usr/bin/env python3
"""demo_metaloop.py — Self-Reconfiguring Agent Loop"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metaloop import MetaLoop, LoopArchitecture, AgentEvent

random.seed(42)

def agent_fn(task, architecture, context_events):
    events = []
    tools = ['search', 'read_file', 'terminal', 'browser', 'write']
    turns = 25
    streak, last_tool = 0, 'search'

    for t in range(turns):
        # Respect architecture's consecutive tool limit
        if streak >= architecture.max_consecutive_same_tool:
            alt = [x for x in tools if x != last_tool]
            if architecture.enabled_tools:
                alt = [x for x in alt if x in architecture.enabled_tools]
            tool = random.choice(alt) if alt else last_tool
            streak = 1
        else:
            if last_tool and random.random() < 0.7:
                tool, streak = last_tool, streak + 1
            else:
                tool, streak = random.choice(tools), 1
        last_tool = tool

        tn = len(context_events) + len(events)
        events.append(AgentEvent(type='tool_call', turn=tn, tool=tool))
        events.append(AgentEvent(type='tool_result', turn=tn, tool=tool, success=random.random() > 0.3))

        # Reflection follows architecture mode
        reflect = architecture.reasoning_mode in ('reflection_first', 'verify_then_output', 'plan_then_execute')
        if not reflect and architecture.force_reflection_after_failures > 0:
            f = sum(1 for e in events[-10:] if e.type == 'tool_result' and e.success is False)
            reflect = f >= architecture.force_reflection_after_failures
        if reflect:
            events.append(AgentEvent(type='reasoning', turn=tn, content='reflecting'))

    return f'done {turns} turns', events

# Start permissive — agent WILL loop
arch = LoopArchitecture(
    reasoning_mode='react',
    max_history_turns=15,
    max_consecutive_same_tool=12,
    force_reflection_after_failures=10,
    temperature=0.7,
)

ml = MetaLoop(agent_fn, arch, detect_every_n_turns=2)
ml.max_reconfigurations = 15
result = ml.run('test')

print('META LOOP — Self-Reconfiguring Agent Loop')
print('=' * 60)
print()
print('Initial: react, 15t history, 12 consecutive, 0.7 temp')
print()
for r in result['reconfigurations']:
    old, new = r['old_arch'], r['new_arch']
    changes = [f'{k}: {v} -> {new[k]}' for k, v in old.items() if v != new[k]]
    if changes:
        print(f'  {r["stage"]:>10s} t~{r["turn"]} ({r["confidence"]:.0%}) | {"; ".join(changes)}')
print()
print('Final architecture:')
for k, v in result['final_architecture'].items():
    print(f'  {k:40s} {v}')
reconf_count = len(result['reconfigurations'])
print(f'\nReconfigurations: {reconf_count}')
print(f'Final stage: {result["final_recovery"].stage}')
print()
print('Breakthrough: No agent system reconfigures its own loop at runtime.')
print('The MetaLoop detects degradation, then redesigns the reinforcement')
print('structure — exactly what the addiction model demands.')
print('=' * 60)
