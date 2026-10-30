# Model Evaluation Results

This document records the anomaly-detector experiments currently available in the project evaluation artifacts. These are **offline benchmark results**, not measured production incident-detection rates.

## 1. V2 original and tuned experiments

Source artifacts: `data/evaluation/evaluation_summary.json` and `data/evaluation/final_v2_comparison.csv`.

Both configurations were evaluated using a 70/30 chronological split with synthetic anomalies.

| Metric | V2 original | V2 tuned |
|---|---:|---:|
| Test samples | 764 | 764 |
| True negatives (TN) | 372 | 365 |
| False positives (FP) | 10 | 17 |
| False negatives (FN) | 203 | 125 |
| True positives (TP) | 179 | 257 |
| Accuracy | 72.12% | 81.41% |
| Precision | 94.71% | 93.80% |
| Recall | 46.86% | 67.28% |
| F1 score | 62.70% | 78.39% |
| False-positive rate | 2.62% | 4.45% |

The tuned V2 configuration used 400 Isolation Forest estimators and contamination 0.055. It improved recall, accuracy, and F1 compared with the original V2 configuration, while precision decreased slightly.

## 2. V3 evaluation

Source artifact: `data/evaluation/v3_evaluation_summary.json`.

The V3 evaluation used a chronological 60/20/20 split, per-service Isolation Forest models, robust median/MAD feature transformations, and a threshold selected using validation data.

| Metric | V3 |
|---|---:|
| Test samples | 510 |
| True negatives (TN) | 237 |
| False positives (FP) | 18 |
| False negatives (FN) | 82 |
| True positives (TP) | 173 |
| Accuracy | 80.39% |
| Precision | 90.58% |
| Recall | 67.84% |
| F1 score | 77.58% |
| False-positive rate | 7.06% |

Per-service results:

| Service | Precision | Recall | F1 | False-positive rate |
|---|---:|---:|---:|---:|
| Order | 100.00% | 66.67% | 80.00% | 0.00% |
| Payment | 98.18% | 64.29% | 77.70% | 1.19% |
| User | 78.75% | 72.41% | 75.45% | 19.54% |

V3 detected all injected request-rate spikes in the reported per-anomaly-type evaluation. Error-ratio spike recall was 0% for Order and Payment and 17.24% for User. This limitation is important: the source dataset's error-ratio feature was constant, so injected error-ratio spikes tested an artificial feature shift.

## 3. Later fair V2/V3 comparison

A separate fair-comparison experiment is recorded in the project evaluation history. It used `metrics_dataset_v2.csv`, a chronological 60/20/20 split per service, and synthetic anomaly injections. The V2 raw-feature and V3 transformed-feature variants produced the same aggregate test confusion matrix in that run:

| Metric | V2 | V3 |
|---|---:|---:|
| Test samples | 510 | 510 |
| TN | 207 | 207 |
| FP | 48 | 48 |
| FN | 69 | 69 |
| TP | 186 | 186 |
| Accuracy | 77.06% | 77.06% |
| Precision | 79.49% | 79.49% |
| Recall | 72.94% | 72.94% |
| F1 score | 76.07% | 76.07% |
| False-positive rate | 18.82% | 18.82% |

This fair comparison is a distinct experiment and must not be merged with the V2 70/30 or V3 60/20/20 results above. Its test false-positive rate exceeded the validation target of 5%, showing that the target did not generalize to the held-out test set.

## 4. How to interpret these metrics

- **Precision** answers: of the observations flagged as anomalous, what proportion were injected/labelled anomalies in this benchmark?
- **Recall** answers: of the injected/labelled anomalies, what proportion did the detector flag?
- **False-positive rate (FPR)** answers: of the observations treated as normal in the benchmark, what proportion were incorrectly flagged?
- **F1** is the harmonic mean of precision and recall.

For an automated recovery workflow, false positives matter because an incorrect anomaly signal can lead to unnecessary remediation. Recall also matters because missed incidents may remain undetected. Threshold selection should therefore consider both metrics and the operational cost of false alarms versus missed incidents.

## 5. Evaluation limitations

1. The original held-out observations are assumed normal; they are not independently verified incident-free ground truth.
2. Injected anomalies are synthetic controlled scenarios, not confirmed production incidents.
3. The source error-ratio feature is constant in the dataset used by the V3 evaluation; its injected spikes are artificial feature-shift tests.
4. The V2 and V3 evaluation scripts use different split strategies, sample counts, and feature pipelines. Their results are not a strict head-to-head comparison unless run through the same dataset, split, labels, and threshold protocol.
5. These metrics describe performance on the documented offline benchmarks only. They do not establish production accuracy, operational reliability, or safe autonomous remediation.

## 6. Recommended reporting

When presenting results, always name the model version and evaluation protocol alongside the metric. For example:

> In the V2 tuning experiment (70/30 chronological split with synthetic anomalies), the tuned configuration achieved 93.80% precision, 67.28% recall, and 78.39% F1. In a separate V3 evaluation (60/20/20 chronological split), V3 achieved 90.58% precision, 67.84% recall, and 77.58% F1. These are synthetic-anomaly benchmark results, not production incident-detection rates.

Do not report precision alone as overall model accuracy. Include recall, F1, false-positive rate, test-set size, and the evaluation limitations.
