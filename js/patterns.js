/**
 * Cognoscope — Pattern Archive Dashboard
 *
 * Cross-session degradation memory display.
 * Shows archived patterns, match predictions, and
 * pre-configuration recommendations.
 *
 * Bridge #40: Cross-Session Agent Memory
 */

const PatternDisplay = (() => {
  "use strict";

  // ──────────────────────────────────────────────
  // 1. MOCK PATTERN ARCHIVE DATA
  // ──────────────────────────────────────────────

  // In production, this queries ~/.hermes/pattern_archive.json
  const DEFAULT_PATTERNS = [
    {
      pattern_id: "PAT_0001",
      name: "Search Escalation Loop",
      stage: "stage_3",
      trigger_signals: ["MAX_RUN_8+", "FEEDBACK_DELAY", "ESCALATION"],
      intervention: "navitoclax (verify_then_output, consec=1, temp=0.3)",
      outcome: "recovered",
      times_seen: 2,
      avg_recovery_turns: 3.5,
    },
    {
      pattern_id: "PAT_0002",
      name: "Tool Narrowing + Overconfidence",
      stage: "stage_2",
      trigger_signals: ["DIVERSITY_DROP", "PFC_FAILURE", "LOW_REFLECTION"],
      intervention: "quercetin (reflection_first, consec=3, certainty=on)",
      outcome: "recovered",
      times_seen: 1,
      avg_recovery_turns: 5.0,
    },
  ];

  let archive = JSON.parse(JSON.stringify(DEFAULT_PATTERNS));

  // ──────────────────────────────────────────────
  // 2. PREDICTION (Jaccard similarity matching)
  // ──────────────────────────────────────────────

  function predict(currentSignals, currentStage) {
    if (!currentSignals || currentSignals.length === 0) return null;

    var bestMatch = null;
    var bestScore = 0;
    var currentSet = new Set(currentSignals);

    archive.forEach(function (pattern) {
      var patternSet = new Set(pattern.trigger_signals);
      var intersection = 0;
      currentSet.forEach(function (s) {
        if (patternSet.has(s)) intersection++;
      });
      // Compute union size manually (avoid spread syntax for compatibility)
      var union = currentSet.size;
      patternSet.forEach(function (s) {
        if (!currentSet.has(s)) union++;
      });
      if (union === 0) return;

      var sim = intersection / union;

      // Stage bonus
      if (currentStage && currentStage === pattern.stage) sim += 0.2;
      // Experience bonus
      if (pattern.times_seen >= 2) sim += 0.1;

      if (sim > bestScore) {
        bestScore = sim;
        bestMatch = pattern;
      }
    });

    if (bestScore >= 0.3) {
      var pred = {
        pattern_id: bestMatch.pattern_id,
        pattern_name: bestMatch.name,
        similarity: Math.round(bestScore * 100),
        predicted_stage: bestMatch.stage,
        recommended_intervention: bestMatch.intervention,
        times_seen: bestMatch.times_seen,
        avg_recovery_turns: bestMatch.avg_recovery_turns,
        warning:
          "Early signs match '" +
          bestMatch.name +
          "' (seen " +
          bestMatch.times_seen +
          "x, " +
          bestMatch.outcome +
          ")",
      };
      return pred;
    }

    return null;
  }

  // ──────────────────────────────────────────────
  // 3. RENDER
  // ──────────────────────────────────────────────

  var panel = null;

  function init(panelId) {
    panel = document.getElementById(panelId);
  }

  function render(events, detectorScores) {
    if (!panel) return;

    // Extract signals from current events
    var signals = extractSignals(events, detectorScores);
    var stage = extractStage(detectorScores);

    // Run prediction
    var prediction = predict(signals, stage);

    var html = "";

    // Status indicator
    if (prediction) {
      html +=
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;border:1px solid var(--amber);border-radius:8px;background:#fef3c7;">';
      html +=
        '  <span style="font-size:16px;font-weight:700;color:#92400e;">!</span>';
      html +=
        '  <div style="font-size:13px;color:#92400e;font-weight:500;">' +
        prediction.warning +
        "</div>";
      html += "</div>";

      // Pre-configuration recommendation
      html +=
        '<div style="margin-bottom:10px;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--code-bg);">';
      html +=
        '  <div style="font-size:12px;font-weight:600;color:var(--muted);margin-bottom:4px;">PRE-CONFIGURE RECOMMENDATION</div>';
      html +=
        '  <div style="font-size:14px;font-weight:600;">' +
        prediction.recommended_intervention +
        "</div>";
      html += '  <div style="display:flex;gap:16px;margin-top:6px;font-size:12px;color:var(--muted);">';
      html +=
        '    <span>Match: <strong>' + prediction.similarity + "%</strong></span>";
      html +=
        '    <span>Pattern: <strong>' +
        prediction.pattern_id +
        "</strong></span>";
      html +=
        '    <span>Expected recovery: <strong>~' +
        prediction.avg_recovery_turns +
        " turns</strong></span>";
      html += "  </div>";
      html += "</div>";
    } else {
      html +=
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;border:1px solid var(--green);border-radius:8px;background:#d1fae5;">';
      html +=
        '  <span style="font-size:13px;color:var(--green);">\u2713 No matching degradation patterns detected.</span>';
      html += "</div>";
    }

    // Archive summary
    html +=
      '<div style="font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px;">ARCHIVE (' +
      archive.length +
      " patterns)</div>";

    archive.forEach(function (p) {
      var stageColor =
        p.stage === "stage_3"
          ? "var(--red)"
          : p.stage === "stage_2"
            ? "var(--amber)"
            : "var(--green)";
      var signals = p.trigger_signals.join(", ");
      html +=
        '<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border);">';
      html +=
        '  <span style="font-weight:600;color:' +
        stageColor +
        ';font-family:monospace;font-size:11px;">' +
        p.pattern_id +
        "</span>";
      html +=
        '  <span style="flex:1;">' + p.name + "</span>";
      html +=
        '  <span style="color:var(--muted);font-size:11px;">' +
        p.times_seen +
        "x | ~" +
        p.avg_recovery_turns +
        "t</span>";
      html += "</div>";
      if (signals) {
        html +=
          '<div style="font-size:10px;color:var(--muted);padding-left:48px;padding-bottom:4px;">' +
          signals +
          "</div>";
      }
    });

    panel.innerHTML = html;
  }

  // ──────────────────────────────────────────────
  // 4. SIGNAL EXTRACTION (from events + scores)
  // ──────────────────────────────────────────────

  function extractSignals(events, scores) {
    var signals = [];

    if (!events || events.length < 3) return signals;

    var tools = events
      .filter(function (e) {
        return e.type === "tool_call" && e.tool;
      })
      .map(function (e) {
        return e.tool;
      });
    var toolCalls = events.filter(function (e) {
      return e.type === "tool_call";
    });
    var reflections = events.filter(function (e) {
      return e.type === "reasoning";
    });

    // Consecutive run
    var maxRun = 1,
      curRun = 1;
    for (var i = 1; i < tools.length; i++) {
      if (tools[i] === tools[i - 1]) {
        curRun++;
        if (curRun > maxRun) maxRun = curRun;
      } else {
        curRun = 1;
      }
    }

    if (maxRun >= 13) signals.push("MAX_RUN_13+");
    else if (maxRun >= 8) signals.push("MAX_RUN_8+");
    else if (maxRun >= 5) signals.push("MAX_RUN_5+");
    else if (maxRun >= 3) signals.push("MAX_RUN_3+");

    // Reflection ratio
    var ratio = reflections.length / Math.max(toolCalls.length, 1);
    if (ratio < 0.1 && toolCalls.length >= 10) signals.push("FEEDBACK_DELAY");
    else if (ratio < 0.2 && toolCalls.length >= 5)
      signals.push("LOW_REFLECTION");

    // Scores
    if (scores) {
      if (scores.escalation > 0.4) signals.push("ESCALATION");
      if (scores.drift > 0.4) signals.push("DIVERSITY_DROP");
      if (scores.overconfidence > 0.5) signals.push("PFC_FAILURE");
    }

    return signals;
  }

  function extractStage(scores) {
    if (!scores) return null;
    if (scores.stage) return scores.stage;

    // Infer from scores
    if (scores.escalation > 0.7) return "stage_3";
    if (scores.escalation > 0.4) return "stage_2";
    if (scores.drift > 0.3) return "stage_2";
    return "stage_1";
  }

  // ──────────────────────────────────────────────
  // 5. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    init: init,
    render: render,
    predict: predict,
    getArchive: function () {
      return archive;
    },
    setArchive: function (a) {
      archive = a;
    },
  };
})();
