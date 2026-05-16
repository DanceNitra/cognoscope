/**
 * Cognoscope — Thompson Sampling Bandit
 * 
 * Learns which interventions work best per bias × agent configuration.
 * Uses a Beta-Bernoulli model (Thompson sampling) to balance
 * exploration vs exploitation of intervention strategies.
 *
 * Each arm = (bias_key, severity) combo.
 * Reward = 1 if post-intervention bias score drops below threshold within N turns.
 * Reward = 0 if it doesn't.
 */

const Bandit = (() => {
  'use strict';

  // ──────────────────────────────────────────────
  // 1. STATE
  // ──────────────────────────────────────────────

  // armId -> { alpha, beta, n_pulls, last_updated }
  let arms = {};

  // Arm key = "biasKey:severity"
  function armId(biasKey, severity) {
    return biasKey + ':' + severity;
  }

  // ──────────────────────────────────────────────
  // 2. INIT / RESET
  // ──────────────────────────────────────────────

  function init() {
    const biases = [
      'anchoring', 'confirmation_bias', 'escalation',
      'overconfidence', 'loss_aversion', 'framing_effects',
      'drift', 'feedback_delay'
    ];
    const severities = ['mild', 'moderate', 'strong'];

    biases.forEach(b => {
      severities.forEach(s => {
        const id = armId(b, s);
        if (!arms[id]) {
          arms[id] = { alpha: 1, beta: 1, n_pulls: 0, last_updated: Date.now() };
        }
      });
    });
  }

  function reset() {
    arms = {};
    init();
  }

  // ──────────────────────────────────────────────
  // 3. SELECT ARM (Thompson sampling)
  // ──────────────────────────────────────────────

  function selectSeverity(biasKey) {
    const severities = ['mild', 'moderate', 'strong'];
    let bestScore = -1;
    let bestSeverity = 'mild';

    severities.forEach(s => {
      const id = armId(biasKey, s);
      const arm = arms[id];
      if (!arm) return;

      // Sample from Beta(alpha, beta)
      // This is the Thompson sampling magic: we sample from the posterior,
      // not just take the mean. Arms with high uncertainty get explored.
      const alpha = arm.alpha;
      const beta = arm.beta;
      const sample = sampleBeta(alpha, beta);

      if (sample > bestScore) {
        bestScore = sample;
        bestSeverity = s;
      }
    });

    return bestSeverity;
  }

  // Sample from Beta distribution (Marsaglia & Tsang method)
  function sampleBeta(alpha, beta) {
    if (alpha <= 0 || beta <= 0) return 0.5;
    if (alpha === 1 && beta === 1) return Math.random();  // uniform

    const a = alpha;
    const b = beta;

    // Use gamma approximation for large values
    if (a > 1 && b > 1) {
      const X = sampleGamma(a);
      const Y = sampleGamma(b);
      return X / (X + Y);
    }

    // Brute force for small values
    return a / (a + b) + (Math.random() - 0.5) * 0.1;
  }

  function sampleGamma(shape) {
    // Marsaglia & Tsang method for shape > 1
    if (shape < 1) return 0;

    let d, c, x, v, u;
    d = shape - 1 / 3;
    c = 1 / Math.sqrt(9 * d);

    while (true) {
      x = 0;
      v = 0;
      while (v <= 0) {
        x = normalRandom();
        v = 1 + c * x;
      }
      v = v * v * v;
      u = Math.random();
      if (u < 1 - 0.0331 * (x * x) * (x * x)) return d * v;
      if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
    }
  }

  // Box-Muller transform for normal sampling
  function normalRandom() {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  }

  // ──────────────────────────────────────────────
  // 4. UPDATE AFTER OBSERVATION
  // ──────────────────────────────────────────────

  function update(biasKey, severity, reward) {
    const id = armId(biasKey, severity);
    const arm = arms[id];
    if (!arm) return false;

    arm.n_pulls++;
    arm.last_updated = Date.now();

    if (reward > 0) {
      arm.alpha += reward;
    } else {
      arm.beta += 1;
    }

    return true;
  }

  // ──────────────────────────────────────────────
  // 5. QUERY
  // ──────────────────────────────────────────────

  function getStats(biasKey) {
    const severities = ['mild', 'moderate', 'strong'];
    return severities.map(s => {
      const id = armId(biasKey, s);
      const arm = arms[id] || { alpha: 1, beta: 1, n_pulls: 0 };
      const total = arm.alpha + arm.beta;
      return {
        severity: s,
        alpha: arm.alpha,
        beta: arm.beta,
        mean: arm.alpha / Math.max(total, 1),
        pulls: arm.n_pulls
      };
    });
  }

  function getAllStats() {
    return Object.keys(arms).map(id => {
      const [biasKey, severity] = id.split(':');
      const arm = arms[id];
      return {
        arm: id,
        biasKey,
        severity,
        alpha: arm.alpha,
        beta: arm.beta,
        mean: arm.alpha / Math.max(arm.alpha + arm.beta, 1),
        pulls: arm.n_pulls
      };
    });
  }

  function getState() {
    return JSON.parse(JSON.stringify(arms));
  }

  function loadState(state) {
    arms = state;
  }

  // ──────────────────────────────────────────────
  // 6. PUBLIC API
  // ──────────────────────────────────────────────

  return {
    init,
    reset,
    selectSeverity,
    update,
    getStats,
    getAllStats,
    getState,
    loadState
  };
})();

// Auto-initialize
Bandit.init();
