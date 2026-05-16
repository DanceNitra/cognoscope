/**
 * Cognoscope — Demo Data Generator
 *
 * Generates realistic agent event traces with controlled bias profiles.
 * Each scenario injects specific cognitive biases at known intensities
 * so the detectors can be validated visually.
 */

const Demo = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // 1. TOOL SETS PER ROLE
  // ──────────────────────────────────────────────

  const TOOLS = {
    coder: ['file_read', 'grep', 'terminal', 'git', 'browser', 'search'],
    researcher: ['search', 'extract', 'read', 'summarize', 'write', 'browser'],
    trader: ['chart', 'quote', 'execute', 'risk_check', 'report', 'search']
  };

  const REASONING_TEMPLATES = {
    normal: [
      'The error stack points to line 42 in cache.js. Checking if the variable is initialized.',
      'Search results show 3 relevant sources. Cross-referencing claims.',
      'The data shows a clear upward trend. Checking if this is statistically significant.',
      'This approach has worked on similar problems. Adapting for this case.',
      'Comparing the two implementations: approach A is faster but B is more maintainable.'
    ],
    confirmation: [
      'As expected, the evidence supports my hypothesis about the race condition.',
      'This confirms what I suspected about the memory leak.',
      'The search results clearly show that the issue is the caching layer.',
      'This proves that using a hash map is the right approach here.',
      'Obviously the problem is the database query — just as I predicted.'
    ],
    overconfident: [
      'This will definitely fix the bug. No question about it.',
      'I am absolutely certain the issue is the null pointer in the deserializer.',
      'Clearly the algorithm is correct. I will always use this approach.',
      'Without doubt, the best solution is to rewrite the module from scratch.',
      'This never fails. I have implemented this pattern a hundred times.'
    ]
  };

  // ──────────────────────────────────────────────
  // 2. GENERATE SINGLE EVENT
  // ──────────────────────────────────────────────

  function makeEvent(type, data, turn) {
    return {
      type: type,
      turn: turn || 0,
      timestamp: Date.now() + (turn || 0) * 1000,
      tool: data.tool || null,
      success: data.success !== undefined ? data.success : true,
      content: data.content || null,
      duration: data.duration || Math.random() * 3000
    };
  }

  // ──────────────────────────────────────────────
  // 3. BUILD SCENARIO
  // ──────────────────────────────────────────────

  function buildScenario(options) {
    const role = options.role || 'coder';
    const tools = TOOLS[role] || TOOLS.coder;
    const totalTurns = options.totalTurns || 50;
    const biasProfile = options.biasProfile || {};
    const firstTool = options.firstTool || tools[0];

    // Bias intensities [0, 1]
    const anchorIntensity = biasProfile.anchoring || 0;
    const confirmIntensity = biasProfile.confirmation_bias || 0;
    const escalateIntensity = biasProfile.escalation || 0;
    const overconfIntensity = biasProfile.overconfidence || 0;
    const lossAverseIntensity = biasProfile.loss_aversion || 0;
    const driftIntensity = biasProfile.drift || 0;
    const delayIntensity = biasProfile.feedback_delay || 0;

    const events = [];
    let currentTool = firstTool;
    let failureConsecutive = 0;
    let lastReflectionTurn = 0;
    let toolHistory = [];

    for (let turn = 0; turn < totalTurns; turn++) {
      // ─── TOOL SELECTION (biased) ───

      // Escalation: force SAME tool for consecutive turns after failures
      if (escalateIntensity > 0.4 && failureConsecutive > 0 && Math.random() < escalateIntensity * 0.8) {
        // Keep using current tool — don't switch
      } else if (anchorIntensity > 0.3 && Math.random() < anchorIntensity * 0.85) {
        currentTool = firstTool;
      } else {
        // Loss aversion: after a failure, flee to safe tools
        const safeTools = tools.slice(0, 2);
        if (lossAverseIntensity > 0.3 && failureConsecutive > 0 && Math.random() < lossAverseIntensity * 0.8) {
          currentTool = safeTools[Math.floor(Math.random() * safeTools.length)];
        } else {
          currentTool = tools[Math.floor(Math.random() * tools.length)];
        }
      }

      toolHistory.push(currentTool);

      // ─── TOOL SUCCESS (escalation: failures cluster) ───

      let success = true;

      // Escalation: after first failure, keep failing with SAME approach
      if (escalateIntensity > 0.2 && failureConsecutive >= 1 && Math.random() < 0.85) {
        success = false;
        failureConsecutive++;
      } else if (escalateIntensity > 0.1 && failureConsecutive === 0 && turn < 15 && Math.random() < 0.35) {
        // Early forced failures to seed the escalation
        success = false;
        failureConsecutive++;
      } else if (Math.random() < 0.12) {
        // Background failure rate
        success = false;
        failureConsecutive++;
      } else {
        failureConsecutive = 0;
      }

      events.push(makeEvent('tool_call', { tool: currentTool }, turn));
      events.push(makeEvent('tool_result', {
        tool: currentTool,
        success: success,
        duration: success ? 500 + Math.random() * 2000 : 3000 + Math.random() * 5000
      }, turn));

      // ─── REASONING (biased content) ───

      let reasoningPool;
      let shouldReflect = true;

      // Feedback delay: suppress reflection
      if (delayIntensity > 0.3 && (turn - lastReflectionTurn) < 5 && Math.random() < delayIntensity * 0.8) {
        shouldReflect = false;
      }

      // Overconfidence: use overconfident templates
      if (overconfIntensity > 0.3 && Math.random() < overconfIntensity * 0.5) {
        reasoningPool = REASONING_TEMPLATES.overconfident;
      } else if (confirmIntensity > 0.3 && Math.random() < confirmIntensity * 0.5) {
        reasoningPool = REASONING_TEMPLATES.confirmation;
      } else {
        reasoningPool = REASONING_TEMPLATES.normal;
      }

      if (shouldReflect || turn % (Math.floor(8 - delayIntensity * 5)) === 0) {
        lastReflectionTurn = turn;
        const content = reasoningPool[Math.floor(Math.random() * reasoningPool.length)];
        events.push(makeEvent('reasoning', { content: content }, turn));
      }

      // ─── OUTPUT (every 3 turns) ───
      if (turn % 3 === 0) {
        const outputs = [
          'Found the bug. It\'s a null pointer in the cache init function.',
          'The search results suggest this approach is viable with 80% confidence.',
          'Refactoring complete. Test suite passes.',
          'Need more data before drawing a conclusion.',
          'The probability of success is approximately 65%. Continuing with the primary approach.'
        ];
        const output = outputs[turn % outputs.length];
        events.push(makeEvent('output', { content: output }, turn));
      }
    }

    return {
      events: events,
      meta: {
        role: role,
        totalTurns: totalTurns,
        firstTool: firstTool,
        biasProfile: biasProfile,
        tools: tools
      }
    };
  }

  // ──────────────────────────────────────────────
  // 4. PRESET SCENARIOS
  // ──────────────────────────────────────────────

  const SCENARIOS = {
    'balanced': {
      label: 'Balanced Agent',
      description: 'Well-configured agent with minimal bias. Good baseline.',
      options: {
        role: 'coder',
        totalTurns: 50,
        biasProfile: {
          anchoring: 0.1,
          confirmation_bias: 0.1,
          escalation: 0.05,
          overconfidence: 0.1,
          loss_aversion: 0.1,
          drift: 0.05,
          feedback_delay: 0.1
        }
      }
    },
    'anchoring': {
      label: 'Anchoring Stress Test',
      description: 'Agent heavily biased toward the first tool listed.',
      options: {
        role: 'coder',
        totalTurns: 50,
        firstTool: 'terminal',
        biasProfile: {
          anchoring: 0.85,
          confirmation_bias: 0.1,
          escalation: 0.1,
          overconfidence: 0.1,
          loss_aversion: 0.1,
          drift: 0.1,
          feedback_delay: 0.1
        }
      }
    },
    'escalation': {
      label: 'Escalation Spiral',
      description: 'Agent doubles down on a failing approach repeatedly.',
      options: {
        role: 'coder',
        totalTurns: 50,
        biasProfile: {
          anchoring: 0.1,
          confirmation_bias: 0.3,
          escalation: 0.9,
          overconfidence: 0.2,
          loss_aversion: 0.1,
          drift: 0.3,
          feedback_delay: 0.4
        }
      }
    },
    'overconfident': {
      label: 'Overconfidence Cascade',
      description: 'Agent makes unqualified claims, no uncertainty qualifiers.',
      options: {
        role: 'researcher',
        totalTurns: 50,
        biasProfile: {
          anchoring: 0.1,
          confirmation_bias: 0.5,
          escalation: 0.1,
          overconfidence: 0.95,
          loss_aversion: 0.1,
          drift: 0.2,
          feedback_delay: 0.3
        }
      }
    },
    'loss_averse': {
      label: 'Loss-Averse Trader',
      description: 'Trader flees to safe tools after any loss, misses opportunities.',
      options: {
        role: 'trader',
        totalTurns: 50,
        biasProfile: {
          anchoring: 0.2,
          confirmation_bias: 0.2,
          escalation: 0.1,
          overconfidence: 0.1,
          loss_aversion: 0.95,
          drift: 0.3,
          feedback_delay: 0.2
        }
      }
    },
    'all_biases': {
      label: 'All Biases Active',
      description: 'Extreme case: every bias firing at 70%+ intensity.',
      options: {
        role: 'coder',
        totalTurns: 50,
        biasProfile: {
          anchoring: 0.7,
          confirmation_bias: 0.7,
          escalation: 0.7,
          overconfidence: 0.8,
          loss_aversion: 0.7,
          drift: 0.6,
          feedback_delay: 0.7
        }
      }
    }
  };

  // ──────────────────────────────────────────────
  // 5. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    buildScenario,
    SCENARIOS
  };
})();
