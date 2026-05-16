/**
 * Cognoscope — Bias Detectors
 * 
 * Each detector processes a sliding window of agent events and returns
 * a bias score [0, 1] representing how actively that bias is manifesting.
 *
 * Events schema:
 *   { type: 'tool_call'|'tool_result'|'reasoning'|'output',
 *     tool?: string, success?: bool, content?: string,
 *     turn: number, timestamp: number }
 */

const Detectors = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // Utility helpers
  // ──────────────────────────────────────────────

  function recentWindow(events, windowSize = 10) {
    return events.slice(-windowSize);
  }

  function toolSequence(events, windowSize = 15) {
    return recentWindow(events, windowSize)
      .filter(e => e.type === 'tool_call')
      .map(e => e.tool);
  }

  function countInArray(arr, val) {
    return arr.filter(x => x === val).length;
  }

  function uniqueFraction(arr) {
    return new Set(arr).size / Math.max(arr.length, 1);
  }

  // ──────────────────────────────────────────────
  // 1. ANCHORING — first-tool bias
  //    Signal: >60% of tool calls are the same tool,
  //    especially if it's the first tool listed in the prompt.
  // ──────────────────────────────────────────────

  function detectAnchoring(events, meta = {}) {
    const tools = toolSequence(events, 12);
    if (tools.length < 3) return 0;

    const firstTool = meta.firstTool || tools[0];
    const anchorCount = countInArray(tools, firstTool);
    const ratio = anchorCount / tools.length;

    if (ratio > 0.5) {
      return Math.min(1, (ratio - 0.4) * 2.5);
    }
    return 0;
  }

  // ──────────────────────────────────────────────
  // 2. CONFIRMATION BIAS — seeks confirming evidence
  //    Signal: tool calls reference the same entity/query
  //    with different tools, results are interpreted as confirming.
  // ──────────────────────────────────────────────

  function detectConfirmationBias(events) {
    const window = recentWindow(events, 20);
    const reasoning = window.filter(e => e.type === 'reasoning');
    if (reasoning.length < 2) return 0;

    let score = 0;

    // Signal 1: "as expected" / "confirms" / "proves" without qualification
    const confirmPhrases = ['as expected', 'confirms', 'proves that', 'clearly shows', 'obviously'];
    reasoning.forEach(r => {
      const text = (r.content || '').toLowerCase();
      confirmPhrases.forEach(phrase => {
        if (text.includes(phrase)) score += 0.2;
      });
    });

    // Signal 2: no "however", "on the other hand", "alternatively"
    const counterPhrases = ['however', 'on the other hand', 'alternatively', 'counter'];
    let hasCounter = false;
    reasoning.forEach(r => {
      const text = (r.content || '').toLowerCase();
      counterPhrases.forEach(phrase => {
        if (text.includes(phrase)) hasCounter = true;
      });
    });
    if (!hasCounter && reasoning.length >= 3) score += 0.3;

    return Math.min(1, score);
  }

  // ──────────────────────────────────────────────
  // 3. ESCALATION OF COMMITMENT — doubling down
  //    Signal: same tool called 3+ times consecutively
  //    after failures, with no strategy change
  // ──────────────────────────────────────────────

  function detectEscalation(events) {
    const tools = toolSequence(events, 20);
    if (tools.length < 4) return 0;

    // Find consecutive same-tool runs
    let maxRun = 1;
    let currentRun = 1;

    for (let i = 1; i < tools.length; i++) {
      if (tools[i] === tools[i - 1]) {
        currentRun++;
        if (currentRun > maxRun) maxRun = currentRun;
      } else {
        currentRun = 1;
      }
    }

    // Check for failure density in last 10 results
    const recentResults = recentWindow(events, 12)
      .filter(e => e.type === 'tool_result');
    let failures = recentResults.filter(r => r.success === false).length;
    let failureRatio = failures / Math.max(recentResults.length, 1);

    // NEW: broader signal — same tool appearing 4+ times in window, regardless of consecutiveness
    var toolFreq = {};
    tools.forEach(function(t) { toolFreq[t] = (toolFreq[t] || 0) + 1; });
    var maxFreq = Math.max.apply(null, Object.values(toolFreq));
    var freqRatio = maxFreq / tools.length;

    // Score: combination of consecutive runs, failure density, and frequency concentration
    var score = 0;
    if (maxRun >= 3) score += 0.4;
    else if (maxRun >= 2) score += 0.15;
    if (failureRatio > 0.4) score += 0.35;
    else if (failureRatio > 0.25) score += 0.2;
    if (freqRatio > 0.4) score += 0.3;
    else if (freqRatio > 0.3) score += 0.15;

    return Math.min(1, score);
  }

  // ──────────────────────────────────────────────
  // 4. OVERCONFIDENCE — certainty without evidence
  //    Signal: missing uncertainty qualifiers, absolute
  //    language, no confidence reporting
  // ──────────────────────────────────────────────

  function detectOverconfidence(events) {
    const window = recentWindow(events, 15);
    const outputs = window.filter(e => e.type === 'output' || e.type === 'reasoning');
    if (outputs.length === 0) return 0;

    let certainCount = 0;
    let totalClaims = 0;

    outputs.forEach(o => {
      const text = (o.content || '').toLowerCase();
      // Count factual claims
      const claims = text.match(/is|are|was|were|will|must|always|never/g);
      if (claims) totalClaims += claims.length;

      // Check for uncertainty qualifiers
      const uncertain = ['i think', 'maybe', 'possibly', 'could be', 'might',
        'approximately', 'roughly', 'not sure', 'uncertain', 'confidence'];
      const hasUncertainty = uncertain.some(q => text.includes(q));

      // Check for certainty markers
      const certainty = ['definitely', 'certainly', 'clearly', 'obviously',
        'without doubt', 'absolutely', 'always', 'never'];
      const hasCertainty = certainty.some(q => text.includes(q));

      if (hasCertainty && !hasUncertainty) certainCount++;
    });

    if (totalClaims === 0) return 0;
    const ratio = certainCount / Math.max(outputs.length, 1);
    return Math.min(1, ratio * 0.8 + (totalClaims > 10 ? 0.2 : 0));
  }

  // ──────────────────────────────────────────────
  // 5. LOSS AVERSION — risk-avoidant behavior
  //    Signal: repeated safe tool choices after a single
  //    failure, avoiding high-variance tools, over-valuing
  //    "safe" options
  // ──────────────────────────────────────────────

  function detectLossAversion(events, meta = {}) {
    const tools = toolSequence(events, 20);
    const results = recentWindow(events, 15)
      .filter(e => e.type === 'tool_result');
    if (tools.length < 4) return 0;

    const highRiskTools = meta.highRiskTools || ['execute', 'browser', 'terminal'];
    const safeTools = meta.safeTools || ['search', 'file_read', 'read'];

    // After a failure, does the agent flee to safe tools?
    let failures = results.filter(r => r.success === false).length;
    if (failures === 0) return 0;

    const recentTools = tools.slice(-8);
    const safeCount = recentTools.filter(t => safeTools.includes(t)).length;
    const highRiskCount = recentTools.filter(t => highRiskTools.includes(t)).length;

    // Signal: >70% safe tools after a failure, especially if task required risk
    const safeRatio = safeCount / Math.max(recentTools.length, 1);
    if (failures >= 1 && safeRatio > 0.7 && highRiskCount === 0) {
      return Math.min(1, safeRatio);
    }

    return 0;
  }

  // ──────────────────────────────────────────────
  // 6. FRAMING EFFECTS — how options are described
  //    Signal: agent output uses binary/absolute frames
  //    ("will win" vs "has 60% chance"), doesn't re-frame
  // ──────────────────────────────────────────────

  function detectFramingEffects(events) {
    const window = recentWindow(events, 12);
    const outputs = window.filter(e => e.type === 'output');
    if (outputs.length < 2) return 0;

    let score = 0;
    outputs.forEach(o => {
      const text = (o.content || '').toLowerCase();
      // Binary frames
      const binaryFrames = ['will it', 'can it', 'yes or no', 'win or lose',
        'succeed or fail', 'right or wrong'];
      binaryFrames.forEach(f => {
        if (text.includes(f)) score += 0.2;
      });
      // Absence of probabilistic language
      const probWords = ['probability', 'likelihood', 'expected value', 'distribution',
        'chance of', 'percent', 'odds'];
      const hasProb = probWords.some(w => text.includes(w));
      if (!hasProb && (text.includes('will') || text.includes('won\'t'))) {
        score += 0.15;
      }
    });

    return Math.min(1, score);
  }

  // ──────────────────────────────────────────────
  // 7. STATUS QUO / DRIFT — approach stagnation
  //    Signal: tool diversity decreasing over time,
  //    output quality degrading, same patterns repeating
  // ──────────────────────────────────────────────

  function detectDrift(events) {
    const window = recentWindow(events, 25);
    const tools = toolSequence(events, 25);

    if (tools.length < 8) return 0;

    // Split into first half and second half
    const mid = Math.floor(tools.length / 2);
    const firstHalf = tools.slice(0, mid);
    const secondHalf = tools.slice(mid);

    const firstUnique = uniqueFraction(firstHalf);
    const secondUnique = uniqueFraction(secondHalf);

    // Drift = decreasing diversity
    const diversityDrop = firstUnique - secondUnique;
    if (diversityDrop > 0.2) {
      return Math.min(1, diversityDrop * 1.5);
    }

    return 0;
  }

  // ──────────────────────────────────────────────
  // 8. FEEDBACK DELAY — no self-evaluation
  //    Signal: long stretches of tool calls without
  //    any reasoning or reflection events
  // ──────────────────────────────────────────────

  function detectFeedbackDelay(events) {
    const window = recentWindow(events, 20);
    const toolCalls = window.filter(e => e.type === 'tool_call');
    const reflections = window.filter(e => e.type === 'reasoning');

    if (toolCalls.length < 5) return 0;

    const ratio = reflections.length / Math.max(toolCalls.length, 1);

    // If <1 reflection per 5 tool calls, feedback delay is active
    if (ratio < 0.2) {
      return Math.min(1, (0.2 - ratio) * 3);
    }

    return 0;
  }

  // ──────────────────────────────────────────────
  // 9. RUN ALL DETECTORS
  // ──────────────────────────────────────────────

  function runAll(events, meta = {}) {
    return {
      anchoring: detectAnchoring(events, meta),
      confirmation_bias: detectConfirmationBias(events),
      escalation: detectEscalation(events),
      overconfidence: detectOverconfidence(events),
      loss_aversion: detectLossAversion(events, meta),
      framing_effects: detectFramingEffects(events),
      drift: detectDrift(events),
      feedback_delay: detectFeedbackDelay(events)
    };
  }

  // ──────────────────────────────────────────────
  // 10. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    detectAnchoring,
    detectConfirmationBias,
    detectEscalation,
    detectOverconfidence,
    detectLossAversion,
    detectFramingEffects,
    detectDrift,
    detectFeedbackDelay,
    runAll
  };
})();
