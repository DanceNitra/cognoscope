/**
 * Senolytic Outcome Simulator
 *
 * Models what happens AFTER each therapy is applied.
 * Each therapy type has a characteristic outcome signature:
 * - Recovery time distribution (how many turns to clear the bias)
 * - Rebound probability (bias coming back)
 * - Collateral damage (side effects on healthy agent function)
 * - SASP suppression (how well error propagation is blocked)
 *
 * Used to close the learning loop: therapy → outcome → record → adapt.
 */

const TherapyOutcome = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // 1. OUTCOME SIGNATURES
  // ──────────────────────────────────────────────

  // Each therapy has a characteristic outcome profile
  // modeled on the biology

  const SIGNATURES = {
    senomorphic: {
      // Fast, shallow, low collateral
      recoveryBase: 2,
      recoveryVariance: 1,
      reboundProb: 0.35,     // SASP suppression only — bias can return
      collateralBase: 0.05,
      saspSuppression: 0.40, // moderate SASP suppression
      biasReduction: 0.30,   // mild — just takes the edge off
      description: 'Mild suppression. Bias reduced but may return.'
    },
    quercetin: {
      // Moderate depth, moderate recovery
      recoveryBase: 4,
      recoveryVariance: 2,
      reboundProb: 0.20,
      collateralBase: 0.12,
      saspSuppression: 0.55,
      biasReduction: 0.50,
      description: 'Soft reset. Bias cut in half, low rebound risk.'
    },
    dasatinib: {
      // Targeted strong effect on one tool pathway
      recoveryBase: 6,
      recoveryVariance: 1,
      reboundProb: 0.10,     // low — tool blacklist prevents recurrence
      collateralBase: 0.25,
      saspSuppression: 0.70,
      biasReduction: 0.65,   // strong effect on escalation-specific bias
      description: 'Tool blocked. Escalation bias eliminated. Moderate collateral.'
    },
    navitoclax: {
      // Deep reset, long recovery, high collateral
      recoveryBase: 10,
      recoveryVariance: 3,
      reboundProb: 0.05,     // almost zero — fresh start
      collateralBase: 0.35,
      saspSuppression: 0.90, // excellent — clears all error signals
      biasReduction: 0.80,
      description: 'Full session clear. Maximum bias reduction. Long recovery cost.'
    },
    car_t: {
      // Precision: high reduction on one bias, near-zero collateral
      recoveryBase: 3,
      recoveryVariance: 1,
      reboundProb: 0.15,
      collateralBase: 0.05,
      saspSuppression: 0.45,
      biasReduction: 0.70,
      description: 'Precision strike. Single bias heavily reduced. Minimal collateral.'
    }
  };

  // ──────────────────────────────────────────────
  // 2. SIMULATE A SINGLE THERAPY APPLICATION
  // ──────────────────────────────────────────────

  function simulate(therapyKey, currentBiasScore, rng) {
    rng = rng || Math.random;
    const sig = SIGNATURES[therapyKey];
    if (!sig) return null;

    // Recovery time: base + noise
    const recoveryTurns = Math.max(1,
      Math.round(sig.recoveryBase + (rng() - 0.5) * 2 * sig.recoveryVariance));

    // Did it rebound?
    const rebounded = rng() < sig.reboundProb;

    // Post-therapy bias score
    const preScore = currentBiasScore;
    const postScore = Math.max(0, preScore * (1 - sig.biasReduction) +
      (rebounded ? preScore * 0.4 * rng() : 0));

    // Collateral damage: how much did healthy function degrade?
    const collateralDamage = sig.collateralBase * (0.5 + rng());

    // SASP suppression effectiveness
    const saspSuppressed = rng() < sig.saspSuppression;

    return {
      therapyKey: therapyKey,
      preScore: Math.round(preScore * 100),
      postScore: Math.round(postScore * 100),
      reduction: Math.round((preScore - postScore) / preScore * 100),
      recoveryTurns: recoveryTurns,
      rebounded: rebounded,
      collateralDamage: Math.round(collateralDamage * 100),
      saspSuppressed: saspSuppressed,
      success: (postScore < preScore * 0.7) && !rebounded,
      netBenefit: Math.round((preScore - postScore) * (1 - collateralDamage) * 100)
    };
  }

  // ──────────────────────────────────────────────
  // 3. COMPARE ALL 5 THERAPIES AGAINST ONE BIAS
  // ──────────────────────────────────────────────

  function compare(biasScore) {
    const results = Object.keys(SIGNATURES).map(function(key) {
      return simulate(key, biasScore);
    });

    // Sort by net benefit (best first)
    results.sort(function(a, b) { return b.netBenefit - a.netBenefit; });

    return results;
  }

  // ──────────────────────────────────────────────
  // 4. RUN FULL SCENARIO (N turns of therapy cycling)
  // ──────────────────────────────────────────────

  function runScenario(therapyKey, initialBias, turns) {
    turns = turns || 20;
    const sig = SIGNATURES[therapyKey];
    if (!sig) return null;

    const trajectory = [];
    let currentBias = initialBias;

    for (let t = 0; t < turns; t++) {
      const outcome = simulate(therapyKey, currentBias);

      trajectory.push({
        turn: t,
        biasBefore: Math.round(currentBias * 100),
        biasAfter: outcome.postScore,
        therapy: therapyKey,
        recoveryTurns: outcome.recoveryTurns
      });

      // Update current bias for next turn
      currentBias = outcome.postScore / 100;

      // Rebound effect: if rebounded, bias increases
      if (outcome.rebounded) {
        currentBias = Math.min(1, currentBias + 0.2);
      }

      // Natural decay: bias tends to decrease slowly without therapy
      if (t % 5 === 0 && currentBias > 0.1) {
        currentBias *= 0.95;
      }
    }

    const finalOutcome = trajectory[trajectory.length - 1];
    return {
      therapy: therapyKey,
      initialBias: Math.round(initialBias * 100),
      finalBias: finalOutcome ? finalOutcome.biasAfter : 0,
      totalReduction: finalOutcome ? Math.round((initialBias - finalOutcome.biasAfter / 100) / initialBias * 100) : 0,
      trajectory: trajectory
    };
  }

  // ──────────────────────────────────────────────
  // 5. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    SIGNATURES,
    simulate,
    compare,
    runScenario
  };
})();
