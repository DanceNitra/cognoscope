/**
 * Senolytic Agent Therapy Engine
 *
 * Implements 5 biologically-inspired therapies for clearing stuck agent states.
 * Maps directly from Bridge #3: Senescent Agents.
 *
 * Therapy tiers:
 *   Senomorphic (mild)   — suppress error propagation without clearing
 *   Quercetin (moderate) — soft reset to last known good state
 *   Dasatinib (strong)   — revoke tool access for stuck-specific tool
 *   Navitoclax (severe)  — full session clearance + restart
 *   CAR-T (targeted)     — precision intervention on detected bias only
 */

const Senolytic = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // 1. THERAPY METADATA
  // ──────────────────────────────────────────────

  const THERAPIES = {
    senomorphic: {
      label: 'Senomorphic',
      drugAnalog: 'Senomorphic (SASP suppressant)',
      description: 'Suppress error propagation without clearing the agent. Filter outputs, block SASP from reaching shared state.',
      severity: 'mild',
      icon: '\u25D1',  // filter
      recoveryTime: 1,  // turns to recover
      collateralDamage: 0.05,  // risk of harming functional behavior
      color: '#2563eb'
    },
    quercetin: {
      label: 'Soft Reset',
      drugAnalog: 'Quercetin / Fisetin',
      description: 'Roll back agent state to last verified healthy checkpoint. Preserves successful outputs, discards the stuck trajectory.',
      severity: 'moderate',
      icon: '\u21A9',
      recoveryTime: 3,
      collateralDamage: 0.15,
      color: '#d97706'
    },
    dasatinib: {
      label: 'Tool Blacklist',
      drugAnalog: 'Dasatinib (tyrosine kinase inhibitor)',
      description: 'Revoke access to the specific tool the agent is stuck on. Agent continues with remaining tools.',
      severity: 'strong',
      icon: '\u2718',
      recoveryTime: 5,
      collateralDamage: 0.25,
      color: '#dc2626'
    },
    navitoclax: {
      label: 'Session Clear',
      drugAnalog: 'Navitoclax (BCL-2 inhibitor)',
      description: 'Full session clearance. Terminate current session, archive diagnostic data, start fresh session.',
      severity: 'severe',
      icon: '\u26A0',
      recoveryTime: 10,
      collateralDamage: 0.40,
      color: '#991b1b'
    },
    car_t: {
      label: 'Targeted Intervention',
      drugAnalog: 'CAR-T cells targeting uPAR',
      description: 'Precision therapy that clears specific bias markers without affecting other agent functions. Cognoscope\'s highest-confidence alert.',
      severity: 'targeted',
      icon: '\u2316',
      recoveryTime: 2,
      collateralDamage: 0.08,
      color: '#16a34a'
    }
  };

  // ──────────────────────────────────────────────
  // 2. THERAPY SELECTION LOGIC
  // ──────────────────────────────────────────────

  function selectTherapy(activeBiases, sessionContext = {}) {
    if (!activeBiases || activeBiases.length === 0) return null;

    const sessionAge = sessionContext.turn || 0;
    const priorInterventions = sessionContext.interventionCount || 0;
    const errorPropagation = sessionContext.saspScore || 0;

    // Rank active biases by priority (1 = highest)
    const sorted = [...activeBiases].sort((a, b) => a.priority - b.priority);
    const topBias = sorted[0];

    let therapyKey = null;

    // Decision tree — biologically motivated

    // CAR-T: precision therapy when only one bias is above threshold
    if (activeBiases.length === 1 && topBias.score >= 0.5 && topBias.score < 0.8) {
      therapyKey = 'car_t';
    }
    // Navitoclax: session clear when SASP is spreading
    else if (errorPropagation > 0.6 || (sessionAge > 40 && activeBiases.length >= 3)) {
      therapyKey = 'navitoclax';
    }
    // Dasatinib: revoke tool access when escalation is the top bias
    else if (topBias.key === 'escalation' && topBias.score >= 0.7) {
      therapyKey = 'dasatinib';
    }
    // Quercetin: soft reset moderate multi-bias or mid-session degradation
    else if (activeBiases.length >= 2 || sessionAge > 25) {
      therapyKey = 'quercetin';
    }
    // Senomorphic: mild single-bias suppression
    else {
      therapyKey = 'senomorphic';
    }

    const therapy = THERAPIES[therapyKey];
    if (!therapy) return null;

    const context = topBias.key === 'escalation' ? { tool: sessionContext.lastTool || 'unknown' } : {};

    return {
      therapyKey: therapyKey,
      therapy: therapy,
      targetBias: topBias,
      activeCount: activeBiases.length,
      sessionAge: sessionAge,
      context: context,
      action: generateAction(therapyKey, topBias, context),
      timestamp: Date.now()
    };
  }

  // ──────────────────────────────────────────────
  // 3. ACTION GENERATION
  // ──────────────────────────────────────────────

  function generateAction(therapyKey, bias, context) {
    const tool = context.tool || 'current_tool';

    switch (therapyKey) {
      case 'senomorphic':
        return {
          type: 'filter',
          instruction: 'Block SASP propagation. Agent outputs are filtered — errors and low-confidence results go to quarantine, not to shared state.',
          effect: 'Stops error contagion without interrupting the agent.',
          tokens: 85
        };

      case 'quercetin':
        return {
          type: 'rollback',
          instruction: 'Soft reset to last checkpoint. Discard last N turns of agent trajectory. Preserve successful tool results.',
          effect: 'Agent resumes from last known good state. Loses context since checkpoint.',
          tokens: 90
        };

      case 'dasatinib':
        return {
          type: 'blacklist',
          instruction: 'Revoke access to ' + tool + '. Agent may continue with all other tools. Tool restored after 5 successful turns on other tools.',
          effect: 'Blocks the specific stuck pathway. Agent forced to diversify tool selection.',
          tokens: 110
        };

      case 'navitoclax':
        return {
          type: 'clear',
          instruction: 'FULL SESSION CLEAR. Archiving current diagnostic data. Starting fresh session. Reason: senescent agent state detected (SASP score > threshold).',
          effect: 'Complete reset. All context lost. Archive for post-mortem.',
          tokens: 95
        };

      case 'car_t':
        return {
          type: 'targeted',
          instruction: 'Precision intervention for ' + bias.label + ' (' + Math.round(bias.score * 100) + '%). Applying specific countermeasure without affecting other agent functions.',
          effect: 'Targeted correction of single bias pathway. Minimal collateral.',
          tokens: 100
        };

      default:
        return { type: 'unknown', instruction: 'Observation only.', effect: 'No action.', tokens: 20 };
    }
  }

  // ──────────────────────────────────────────────
  // 4. THERAPY APPLICATION LOG
  // ──────────────────────────────────────────────

  let therapyLog = [];

  function applyTherapy(activeBiases, sessionContext) {
    const decision = selectTherapy(activeBiases, sessionContext);
    if (!decision) return null;

    therapyLog.push({
      turn: sessionContext.turn || 0,
      therapy: decision.therapyKey,
      targetBias: decision.targetBias ? decision.targetBias.key : 'none',
      action: decision.action,
      timestamp: decision.timestamp
    });

    return decision;
  }

  function getTherapyLog(limit) {
    limit = limit || 20;
    return therapyLog.slice(-limit);
  }

  function clearTherapyLog() {
    therapyLog = [];
  }

  // ──────────────────────────────────────────────
  // 5. THERAPY EFFECTIVENESS TRACKING
  // ──────────────────────────────────────────────

  // Track whether therapies actually reduce bias scores post-application
  let effectiveness = {};

  function recordOutcome(therapyKey, biasKey, postScore, preScore) {
    if (!effectiveness[therapyKey]) {
      effectiveness[therapyKey] = { tried: 0, succeeded: 0, biasResults: {} };
    }
    if (!effectiveness[therapyKey].biasResults[biasKey]) {
      effectiveness[therapyKey].biasResults[biasKey] = { tried: 0, succeeded: 0 };
    }

    effectiveness[therapyKey].tried++;
    effectiveness[therapyKey].biasResults[biasKey].tried++;

    // Success = bias score dropped by at least 30%
    if (postScore < preScore * 0.7) {
      effectiveness[therapyKey].succeeded++;
      effectiveness[therapyKey].biasResults[biasKey].succeeded++;
    }
  }

  function getEffectiveness() {
    const summary = {};
    Object.keys(effectiveness).forEach(key => {
      const e = effectiveness[key];
      summary[key] = {
        label: THERAPIES[key] ? THERAPIES[key].label : key,
        tried: e.tried,
        succeeded: e.succeeded,
        successRate: e.tried > 0 ? Math.round(e.succeeded / e.tried * 100) : 0
      };
    });
    return summary;
  }

  // ──────────────────────────────────────────────
  // 6. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    THERAPIES,
    selectTherapy,
    applyTherapy,
    getTherapyLog,
    clearTherapyLog,
    recordOutcome,
    getEffectiveness
  };
})();
