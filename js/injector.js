/**
 * Cognoscope — Injector
 * 
 * Generates minimal context injections to counter active biases.
 * Each injection is a single line that gets appended to the agent's
 * context window. Designed to be low-token, high-impact.
 *
 * Also tracks post-intervention outcomes for the bandit learner.
 */

const Injector = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // 1. INTERVENTION TEMPLATES
  // ──────────────────────────────────────────────

  const TEMPLATES = {
    anchoring: {
      mild: 'Consider a tool you haven\'t used recently. The first option is not always the best.',
      moderate: 'You\'ve been using {tool} frequently. List 2 other tools that could work before deciding.',
      strong: 'STOP. You\'ve called {tool} {count} times recently. Force yourself to pick a different tool for this turn.'
    },
    confirmation_bias: {
      mild: 'What evidence would disprove your current hypothesis? Check that explicitly.',
      moderate: 'Before concluding, search for evidence AGAINST your position. What would falsify it?',
      strong: 'You appear to be confirming an existing belief. State the strongest counterargument, then refute it with evidence.'
    },
    escalation: {
      mild: '{tool} hasn\'t succeeded in {count} tries. Is there another approach?',
      moderate: 'EScalation alert: same tool, {count} consecutive failures. Describe an alternative strategy before continuing.',
      strong: 'CIRCUIT BREAKER. {count} failures with {tool}. You must propose a different approach and get implicit approval before proceeding.'
    },
    overconfidence: {
      mild: 'Rate your confidence in that last statement (0-100%).',
      moderate: 'Your last output lacked uncertainty qualifiers. Add one: "I\'m X% confident because..."',
      strong: 'OVERCONFIDENCE DETECTED. You made {count} unqualified claims in the last turn. Add uncertainty qualifiers to all of them.'
    },
    loss_aversion: {
      mild: 'Remember: inaction has a cost too. Compare the expected value of action vs inaction.',
      moderate: 'You\'ve been using safe tools exclusively. The risk of missing the right tool is also a loss.',
      strong: 'Loss aversion is narrowing your tool selection. The expected loss from not using {tool} may exceed the expected loss from using it.'
    },
    framing_effects: {
      mild: 'Reframe your task as a probability, not a binary outcome.',
      moderate: 'You\'re using binary frames ("win/lose", "will/won\'t"). Re-express as probabilities: "60% chance of success."',
      strong: 'FRAMING BIAS: "{original_frame}" is a binary frame. Rephrase as: "{reframe}"'
    },
    drift: {
      mild: 'Has your approach changed in the last {count} turns? If not, consider whether it should.',
      moderate: 'Tool diversity is decreasing. Try a tool you haven\'t used recently.',
      strong: 'DRIFT DETECTED. Your last {count} turns show a narrowing pattern. Reflect: "Am I making progress or repeating?"'
    },
    feedback_delay: {
      mild: 'Quick reflection: is your current approach working?',
      moderate: 'NO SELF-EVALUATION IN {count} TURNS. Pause and evaluate: "What have I learned? Am I closer to the goal?"',
      strong: 'FEEDBACK DELAY: {count} tool calls without reflection. Mandatory reflection step before next action.'
    }
  };

  // ──────────────────────────────────────────────
  // 2. GENERATE INJECTION
  // ──────────────────────────────────────────────

  function generate(biasKey, context = {}) {
    const templates = TEMPLATES[biasKey];
    if (!templates) return null;

    // Select severity based on score
    const score = context.score || 0.5;
    let severity;
    if (score < 0.6) severity = 'mild';
    else if (score < 0.8) severity = 'moderate';
    else severity = 'strong';

    let template = templates[severity];

    // Fill placeholders
    template = template.replace(/\{tool\}/g, context.tool || 'current_tool');
    template = template.replace(/\{count\}/g, String(context.count || 3));
    template = template.replace(/\{original_frame\}/g, context.originalFrame || 'will it work?');
    template = template.replace(/\{reframe\}/g, context.reframe || 'What is the probability of success?');

    return {
      text: template,
      severity: severity,
      bias: biasKey,
      tokens: Math.ceil(template.length / 4)  // rough estimate
    };
  }

  // ──────────────────────────────────────────────
  // 3. BATCH GENERATE FOR ALL ACTIVE BIASES
  // ──────────────────────────────────────────────

  function generateAll(activeBiases, context = {}) {
    const injections = [];
    let totalTokens = 0;
    const MAX_TOKENS = 500;  // don't flood the context

    activeBiases.forEach(bias => {
      if (totalTokens >= MAX_TOKENS) return;

      const injection = generate(bias.key, {
        score: bias.score,
        tool: bias.tool,
        count: bias.count
      });

      if (injection) {
        totalTokens += injection.tokens;
        injections.push(injection);
      }
    });

    return injections;
  }

  // ──────────────────────────────────────────────
  // 4. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    TEMPLATES,
    generate,
    generateAll
  };
})();
