/**
 * Cognoscope — Fusion Layer
 * 
 * Takes raw detector scores, applies cooldown windows (suppress
 * repeat firings of the same bias), cross-checks for correlated
 * biases, and returns a ranked list of active interventions.
 *
 * Also tracks which interventions have been applied recently so
 * we don't flood the agent with noise.
 */

const Fusion = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // 1. BIAS METADATA
  // ──────────────────────────────────────────────

  const BIAS_META = {
    anchoring: {
      label: 'Anchoring',
      priority: 3,        // 1=highest, 5=lowest
      cooldownTurns: 8,
      threshold: 0.5,
      color: '#d97706'    // amber
    },
    confirmation_bias: {
      label: 'Confirmation Bias',
      priority: 2,
      cooldownTurns: 10,
      threshold: 0.4,
      color: '#dc2626'    // red
    },
    escalation: {
      label: 'Escalation of Commitment',
      priority: 1,        // highest — can burn tokens fast
      cooldownTurns: 6,
      threshold: 0.4,
      color: '#dc2626'
    },
    overconfidence: {
      label: 'Overconfidence',
      priority: 3,
      cooldownTurns: 10,
      threshold: 0.5,
      color: '#d97706'
    },
    loss_aversion: {
      label: 'Loss Aversion',
      priority: 4,
      cooldownTurns: 12,
      threshold: 0.5,
      color: '#16a34a'    // green
    },
    framing_effects: {
      label: 'Framing Effects',
      priority: 4,
      cooldownTurns: 15,
      threshold: 0.5,
      color: '#6b7280'    // gray
    },
    drift: {
      label: 'Drift / Status Quo',
      priority: 3,
      cooldownTurns: 10,
      threshold: 0.4,
      color: '#d97706'
    },
    feedback_delay: {
      label: 'Feedback Delay',
      priority: 2,
      cooldownTurns: 8,
      threshold: 0.4,
      color: '#2563eb'    // blue
    }
  };

  // ──────────────────────────────────────────────
  // 2. INTERVENTION HISTORY
  // ──────────────────────────────────────────────

  let interventionLog = [];   // { bias, turn, success: null | bool }

  function clearHistory() {
    interventionLog = [];
  }

  function lastIntervention(biasKey) {
    const entries = interventionLog.filter(i => i.bias === biasKey);
    return entries[entries.length - 1] || null;
  }

  function recordIntervention(biasKey, turn) {
    interventionLog.push({
      bias: biasKey,
      turn: turn,
      timestamp: Date.now(),
      success: null   // filled in later when we observe post-intervention behavior
    });
  }

  function recordOutcome(biasKey, turnAfter, wasEffective) {
    for (let i = interventionLog.length - 1; i >= 0; i--) {
      const entry = interventionLog[i];
      if (entry.bias === biasKey && entry.success === null && entry.turn < turnAfter) {
        entry.success = wasEffective;
        return;
      }
    }
  }

  function getHistory() {
    return interventionLog;
  }

  // ──────────────────────────────────────────────
  // 3. FUSION: SCORE → COOLDOWN → PRIORITIZE
  // ──────────────────────────────────────────────

  function fuse(rawScores, currentTurn, options = {}) {
    const results = [];

    Object.keys(rawScores).forEach(key => {
      const score = rawScores[key];
      const meta = BIAS_META[key];
      if (!meta) return;

    // Threshold gate
    if (score < meta.threshold) return;

    // Cooldown check — skip only if very recent (same turn)
    const last = lastIntervention(key);
    if (last && last.turn === currentTurn) return;

      results.push({
        key: key,
        score: score,
        label: meta.label,
        priority: meta.priority,
        color: meta.color,
        turn: currentTurn
      });
    });

    // Sort by priority (1=highest) then by score descending
    results.sort((a, b) => {
      if (a.priority !== b.priority) return a.priority - b.priority;
      return b.score - a.score;
    });

    return results;
  }

  // ──────────────────────────────────────────────
  // 4. RUN FULL CYCLE
  // ──────────────────────────────────────────────

  function cycle(rawScores, currentTurn, options = {}) {
    const active = fuse(rawScores, currentTurn, options);

    // Auto-record interventions for active biases
    active.forEach(b => {
      recordIntervention(b.key, currentTurn);
    });

    return {
      active: active,                    // biases needing intervention, ranked
      allScores: rawScores,              // full signal map (for the radar chart)
      interventionCount: interventionLog.length
    };
  }

  // ──────────────────────────────────────────────
  // 5. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    BIAS_META,
    fuse,
    cycle,
    recordIntervention,
    recordOutcome,
    getHistory,
    clearHistory
  };
})();
