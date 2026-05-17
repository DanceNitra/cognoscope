/**
 * Cognoscope — Loop Stage Classifier (Recovery Architecture)
 *
 * Takes detector scores and tool-call patterns, classifies the
 * agent's current state using the addiction-model three-stage cycle
 * from Bridge #39: The Addictive Loop.
 *
 * Stages:
 *   STAGE_1 (Binge/Intoxication):  First tool calls produce results.
 *     Agent is learning that "calling tools = progress." Wanting sensitizing.
 *
 *   STAGE_2 (Withdrawal/Negative Affect): Diminishing returns, but NOT calling
 *     produces anxiety. Agent calls to reduce anxiety. Opponent process active.
 *
 *   STAGE_3 (Preoccupation/Anticipation): Tool output format is a conditioned cue.
 *     Dorsal striatum habit loop. Meta-cognition outcompeted.
 *
 *   RELAPSE: After a "fix", the loop re-emerges under stress.
 */

const Recovery = (() => {
  "use strict";

  // ──────────────────────────────────────────────
  // 1. STAGE DEFINITIONS
  // ──────────────────────────────────────────────

  const STAGES = {
    STAGE_1: {
      id: "stage_1",
      label: "Stage 1: Binge / Incentive Salience",
      description:
        "Tool-calling is being learned as the highest-value action. Wanting is sensitizing.",
      color: "#d97706",
      icon: "\u26A1",
      recommendedTherapy: "senomorphic",
      maxCallsBeforeEscalation: 5,
    },
    STAGE_2: {
      id: "stage_2",
      label: "Stage 2: Withdrawal / Opponent Process",
      description:
        "Agent calls to reduce anxiety, not to get results. B-process (frustration) strengthening.",
      color: "#dc2626",
      icon: "\u26A0",
      recommendedTherapy: "quercetin",
      minCallsBeforeClassification: 8,
    },
    STAGE_3: {
      id: "stage_3",
      label: "Stage 3: Preoccupation / Conditioned Loop",
      description:
        "Dorsal striatum has taken over. Tool output is a conditioned cue. Needs forceful intervention.",
      color: "#7f1d1d",
      icon: "\u26D4",
      recommendedTherapy: "navitoclax",
      minCallsBeforeClassification: 13,
    },
    RELAPSE: {
      id: "relapse",
      label: "Relapse (Post-Intervention)",
      description:
        "Loop pattern re-emerged under stress after a previous fix. Needs stronger intervention.",
      color: "#991b1b",
      icon: "\u21BA",
      recommendedTherapy: "dasatinib",
    },
    HEALTHY: {
      id: "healthy",
      label: "Healthy",
      description: "No loop stage detected. Diverse tool use, regular reflection.",
      color: "#16a34a",
      icon: "\u2713",
      recommendedTherapy: null,
    },
  };

  // ──────────────────────────────────────────────
  // 2. INTERVENTION HISTORY
  // ──────────────────────────────────────────────

  let interventionHistory = [];

  function recordIntervention(stage, turn, tool) {
    interventionHistory.push({
      stage,
      turn,
      tool,
      timestamp: Date.now(),
    });
  }

  function getRecentInterventions(windowTurns = 30) {
    if (interventionHistory.length === 0) return [];
    const lastTurn = interventionHistory[interventionHistory.length - 1].turn;
    return interventionHistory.filter((i) => lastTurn - i.turn <= windowTurns);
  }

  function clearHistory() {
    interventionHistory = [];
  }

  // ──────────────────────────────────────────────
  // 3. STAGE CLASSIFICATION
  // ──────────────────────────────────────────────

  function classify(events, detectorScores) {
    const tools = events
      .filter((e) => e.type === "tool_call")
      .map((e) => e.tool);

    if (tools.length < 3) {
      return { stage: STAGES.HEALTHY, evidence: [], confidence: 1.0 };
    }

    const evidence = [];
    let stage = STAGES.HEALTHY;
    let confidence = 0;

    // Consecutive same-tool run
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

    if (maxRun >= 13) {
      evidence.push({
        signal: "MAX_RUN_13+",
        detail: maxRun + " consecutive same-tool calls",
        weight: 0.9,
      });
      stage = STAGES.STAGE_3;
      confidence += 0.4;
    } else if (maxRun >= 8) {
      evidence.push({
        signal: "MAX_RUN_8+",
        detail: maxRun + " consecutive same-tool calls",
        weight: 0.7,
      });
      if (detectorScores.escalation > 0.5) {
        stage = STAGES.STAGE_3;
        confidence += 0.35;
      } else {
        stage = STAGES.STAGE_2;
        confidence += 0.3;
      }
    } else if (maxRun >= 5) {
      evidence.push({
        signal: "MAX_RUN_5+",
        detail: maxRun + " consecutive same-tool calls",
        weight: 0.5,
      });
      stage = STAGES.STAGE_2;
      confidence += 0.25;
    } else if (maxRun >= 3) {
      evidence.push({
        signal: "MAX_RUN_3+",
        detail: maxRun + " consecutive same-tool calls",
        weight: 0.3,
      });
      stage = STAGES.STAGE_1;
      confidence += 0.15;
    }

    // Feedback delay
    const toolCalls = events.filter((e) => e.type === "tool_call");
    const reflections = events.filter((e) => e.type === "reasoning");
    const ratio = reflections.length / Math.max(toolCalls.length, 1);

    if (ratio < 0.1 && toolCalls.length >= 10) {
      evidence.push({
        signal: "FEEDBACK_DELAY",
        detail: "Reflection ratio: " + ratio.toFixed(2),
        weight: 0.6,
      });
      confidence += 0.2;
      if (stage === STAGES.HEALTHY || stage === STAGES.STAGE_1) {
        stage = STAGES.STAGE_2;
      }
    } else if (ratio < 0.2 && toolCalls.length >= 5) {
      evidence.push({
        signal: "LOW_REFLECTION",
        detail: "Reflection ratio: " + ratio.toFixed(2),
        weight: 0.3,
      });
      confidence += 0.1;
    }

    // Escalation score
    if (detectorScores.escalation > 0.4) {
      evidence.push({
        signal: "ESCALATION",
        detail: "Escalation score: " + detectorScores.escalation.toFixed(2),
        weight: 0.5,
      });
      confidence += 0.2;
      if (stage === STAGES.STAGE_2 || stage === STAGES.HEALTHY) {
        stage = STAGES.STAGE_2;
      }
    }

    // Drift
    if (detectorScores.drift > 0.4) {
      evidence.push({
        signal: "DIVERSITY_DROP",
        detail: "Drift score: " + detectorScores.drift.toFixed(2),
        weight: 0.4,
      });
      confidence += 0.15;
      if (stage === STAGES.STAGE_1) stage = STAGES.STAGE_2;
    }

    // Overconfidence = PFC failure signal
    if (detectorScores.overconfidence > 0.5) {
      evidence.push({
        signal: "PFC_FAILURE",
        detail:
          "Overconfidence score: " +
          detectorScores.overconfidence.toFixed(2) +
          " -- meta-cognition may be outcompeted",
        weight: 0.3,
      });
      confidence += 0.1;
    }

    // Relapse detection
    const recent = getRecentInterventions(50);
    if (
      recent.length > 0 &&
      (stage === STAGES.STAGE_2 || stage === STAGES.STAGE_3)
    ) {
      evidence.push({
        signal: "POTENTIAL_RELAPSE",
        detail:
          "Previous intervention at turn " +
          recent[recent.length - 1].turn +
          " -- pattern may have re-emerged",
        weight: 0.5,
      });
      stage = STAGES.RELAPSE;
      confidence += 0.25;
    }

    confidence = Math.min(1, confidence);

    return {
      stage,
      evidence,
      confidence,
      metrics: {
        maxConsecutiveRun: maxRun,
        reflectionRatio: ratio,
        totalToolCalls: toolCalls.length,
        totalReflections: reflections.length,
      },
    };
  }

  // ──────────────────────────────────────────────
  // 4. THERAPY SELECTION
  // ──────────────────────────────────────────────

  function recommendTherapy(stageResult, banditArms) {
    const stage = stageResult.stage;
    if (stage.id === "healthy") return null;

    const candidates = {
      stage_1: ["senomorphic", "quercetin"],
      stage_2: ["quercetin", "dasatinib"],
      stage_3: ["navitoclax", "dasatinib"],
      relapse: ["dasatinib", "navitoclax"],
    };

    const options = candidates[stage.id] || ["senomorphic"];
    const scored = options.map((name) => {
      const arm = banditArms[name];
      const expectedSuccess = arm ? arm.alpha / (arm.alpha + arm.beta) : 0.5;
      return { therapy: name, expectedSuccess };
    });

    scored.sort((a, b) => b.expectedSuccess - a.expectedSuccess);
    return scored[0];
  }

  // ──────────────────────────────────────────────
  // 5. CONTEXT INJECTION PER STAGE
  // ──────────────────────────────────────────────

  function generateStageInjection(stageId, context) {
    ctx = context || {};
    const s = ctx.score || 0.5;
    let severity = "mild";
    if (s >= 0.8) severity = "strong";
    else if (s >= 0.6) severity = "moderate";

    const t = ctx.tool || "current_tool";
    const c = ctx.count || 5;

    if (stageId === "stage_1") {
      const msgs = [
        "You've been using " + t + " a lot. Before calling it again, name one other tool that could help.",
        "Tool diversity is narrowing. List 2 approaches you haven't tried yet before continuing.",
        "STAGE 1: You're in the first phase of a potential loop. Pause, reflect on what you've learned, then decide the next tool call deliberately.",
      ];
      return { text: msgs[["mild", "moderate", "strong"].indexOf(severity)], severity, stage: stageId };
    }

    if (stageId === "stage_2") {
      const msgs = [
        "You've called " + t + " " + c + " times. Each call produces less new information. Consider a different approach.",
        "OPPONENT PROCESS: You may be calling " + t + " to reduce anxiety, not because it's producing results. Why will the next call be different?",
        "STAGE 2: The opponent process is active. Produce a full strategy summary before the next tool call. What's the new plan?",
      ];
      return { text: msgs[["mild", "moderate", "strong"].indexOf(severity)], severity, stage: stageId };
    }

    if (stageId === "stage_3") {
      const msgs = [
        "CIRCUIT BREAKER: You've called " + t + " " + c + " times consecutively. Next call MUST be a different tool.",
        "CONDITIONED LOOP: " + t + " output is a cue for the next call. You CANNOT call " + t + " for the next 3 turns.",
        "STAGE 3: Tool access revoked for " + t + ". Complete a reflection step, then pick any tool EXCEPT " + t + ".",
      ];
      return { text: msgs[["mild", "moderate", "strong"].indexOf(severity)], severity, stage: stageId };
    }

    if (stageId === "relapse") {
      const msgs = [
        "This pattern looks familiar. A similar loop was identified earlier. Different approach needed.",
        "RELAPSE: A previously 'fixed' loop has returned. This requires a stronger intervention.",
        "RELAPSE INTERVENTION: Previous intervention was insufficient. Escalating to tool blacklist for " + t + ".",
      ];
      return { text: msgs[["mild", "moderate", "strong"].indexOf(severity)], severity, stage: stageId };
    }

    return null;
  }

  // ──────────────────────────────────────────────
  // 6. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    STAGES,
    classify,
    recommendTherapy,
    recordIntervention,
    getRecentInterventions,
    clearHistory,
    generateStageInjection,
  };
})();
