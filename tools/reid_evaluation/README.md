<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ReID Model Evaluation

Create a repeatable offline scorecard for SceneScape's default
`person-reidentification-retail-0277` model and future replacements. This tool
evaluates labeled person crops or cached vectors without modifying a live gallery.
It does not infer person identities from Tracker IDs.

## Workflow

Follow steps 1-7 for a first baseline on the bundled Queuing video:

```text
Video + person detector
  -> automatic person crops + contact sheets + review.csv
  -> human identity/split review
  -> manifest.json
  -> ReID model inference + similarity scoring
  -> baseline scorecard
  -> replacement model on the same crops/labels -> comparison
```

The **person detector** finds bounding boxes. The **ReID model** turns each crop
into an embedding. They are different models and both are needed for this workflow.
Detection does not determine who a person is: human identity labels are mandatory.

## 1. Install the Tools

Run commands from the repository root:

```bash
python3 -m venv tools/reid_evaluation/.venv
tools/reid_evaluation/.venv/bin/pip install -r tools/reid_evaluation/requirements-crops.txt
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.crops --help
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate --help
```

You need Python 3.11+, disk space for crops, and Docker only if copying models
from a SceneScape volume. Cropping and evaluation themselves run on the host;
Manager, MQTT, Tracker, and the vector database do not need to be running.
All commands below assume the same repository-root working directory.

Cached vectors require only `requirements.txt` (NumPy). OpenVINO and Pillow are
imported only for image inference. The inference requirements intentionally allow
a supported OpenVINO release range; each report records the exact installed
version. Pin it in your experiment environment when comparing models.
For existing crops without video export, install `requirements-inference.txt` instead.

## 2. Prepare the Detector and ReID Models

This example uses these installed FP32 models:

| Role                  | Model                                 |
| --------------------- | ------------------------------------- |
| Person detector       | `person-detection-retail-0013`        |
| Default ReID baseline | `person-reidentification-retail-0277` |

Copy XML/BIN pairs from the model volume to an ignored, host-accessible cache.
The volume is mounted read-only; this does not modify the installed models.

```bash
MODEL_VOLUME=scenescape_vol-models
MODEL_DIR="$PWD/tools/reid_evaluation/output/models"
mkdir -p "$MODEL_DIR"

docker volume inspect "$MODEL_VOLUME" >/dev/null && \
for MODEL_NAME in person-detection-retail-0013 person-reidentification-retail-0277; do
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$MODEL_VOLUME:/models:ro" -v "$MODEL_DIR:/out" \
    alpine:3.23 cp \
    "/models/omz/$MODEL_NAME/FP32/$MODEL_NAME.xml" \
    "/models/omz/$MODEL_NAME/FP32/$MODEL_NAME.bin" /out/
done
```

If your Compose project uses a different volume prefix, change `MODEL_VOLUME`.
If models are not installed, follow the [model installation guide](../../model_download/README.md)
first. Alternatively, put your own compatible IR XML/BIN pairs in `MODEL_DIR`.
Do not use example `/models/...` paths unless that directory actually exists on
your host. Always keep each XML next to its corresponding BIN.

## 3. Export Person Crops From the Video

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.crops export \
  --video sample_data/demo_scenes/Queuing/video/qcam1.mp4 \
  --detector tools/reid_evaluation/output/models/person-detection-retail-0013.xml \
  --camera qcam1 --every-seconds 2 --max-frames 100 \
  --output tools/reid_evaluation/output/queuing-qcam1
```

The exporter supports SSD-style normalized seven-value detections, not arbitrary YOLO models.
It uses BGR/NCHW 0-255 input, model-sized OpenCV bilinear resize, confidence
`0.7`, and minimum clipped crop area `5000` pixels by default. These filters are
configurable. Video timestamps are frame-index/FPS estimates; variable-frame-rate
sources may need separate timestamp handling.

Outputs are `crops/*.png`, paginated `contact-sheet-*.jpg`, `review.csv`, and
`export.json` with source/model hashes and sampling parameters. Existing output
directories are not overwritten. Crops contain people: keep them local and
appropriately access-controlled; the output directory is ignored by Git.

Crop IDs use `<namespace>-f0000000-p00`, where the namespace is the first
24 hexadecimal characters of a SHA-256 hash of the camera ID and recording
content hash. Different cameras or recording contents have different namespaces;
moving or renaming the same recording does not change its IDs. Re-exporting the
same camera/recording reuses the namespace, so do not combine duplicate exports.
The namespace is recorded as `id_namespace` in `export.json`. Contact sheets show
only the readable `f0000000-p00` suffix and timestamp; match these to the full IDs
in that export's `review.csv`. Preserve the full IDs when combining observations.

For another recording, change `--video`, `--camera`, and `--output`. Use the
real camera ID, not an arbitrary identity label. `--max-frames` limits the number
of sampled frames, not the total number of decoded frames or exported crops.
For example, `--every-seconds 2` samples approximately every two seconds.

## 4. Review Crops and Assign Ground Truth

Open `tools/reid_evaluation/output/queuing-qcam1/contact-sheet-*.jpg`, then edit
`tools/reid_evaluation/output/queuing-qcam1/review.csv` in a spreadsheet or text editor.
Preserve all columns, crop IDs, image paths, camera IDs, and row associations.
Only `identity`, `split`, and `include` need to be edited.

- Set `identity` to the same verified person label across observations.
- Assign `split` as `gallery`, `calibration`, or `test`.
- Set `include=no` for false detections, partial/ambiguous crops, or duplicates.
- Crop IDs (`<namespace>-f...-p...`) are not person IDs and must not be used as ground truth.

For a first **fixed-threshold** evaluation, you only need gallery and test rows:

| Crop selected by your review                       | identity   | split     | include |
| -------------------------------------------------- | ---------- | --------- | ------- |
| Clear reference crop of person A                   | `person-a` | `gallery` | `yes`   |
| Different, later crop of the same person A         | `person-a` | `test`    | `yes`   |
| Crop of person B, deliberately absent from gallery | `person-b` | `test`    | `yes`   |
| Partial crop at the frame edge                     | blank      | blank     | `no`    |

These are assignment examples, not pre-labeled identities in the demo footage.
You must verify the people yourself. Keep unknown people out of the entire
gallery, and select gallery/query observations separated in time or tracklet.
Avoid consecutive near-identical frames. Use stable pseudonymous labels such
as `person-a`, not names or guessed Tracker IDs.

### What the Splits Mean

- **Gallery:** enrolled reference crops that queries search against.
- **Calibration:** optional labeled queries used to choose a similarity threshold.
- **Test:** held-out queries used to report final results.

Calibration means threshold selection, not camera calibration or model training.
For `--calibrate`, calibration/test identities must be disjoint, and calibration
needs both known and unknown people. A short video with only a few people may
not support that split; start with the fixed `0.5` threshold rather than inventing
labels or reusing test identities for threshold tuning.

## 5. Generate the Evaluation Manifest

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.crops manifest \
  --review-csv tools/reid_evaluation/output/queuing-qcam1/review.csv \
  --output tools/reid_evaluation/output/queuing-qcam1/manifest.json
```

Unlabeled retained crops are rejected rather than assigned fake identities.
The resulting JSON contains your reviewed labels and absolute crop paths, and
can be passed directly to the evaluator. If you change the review later, write a
new manifest filename; existing manifests are not overwritten.

## 6. Run the Default-Model Baseline

For this single camera, use `--allow-same-camera` with the evaluator and choose
gallery/query crops separated in time/tracklet. This measures within-camera
consistency only, not cross-camera ReID. Add another camera/video and verified
shared identity labels for a representative cross-camera baseline. Calibration
and test identities must still be disjoint when calibrating.

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate \
  --manifest tools/reid_evaluation/output/queuing-qcam1/manifest.json \
  --model tools/reid_evaluation/output/models/person-reidentification-retail-0277.xml \
  --model-version omz-0277-fp32 \
  --allow-same-camera \
  --metric COSINE --threshold 0.5 \
  --output tools/reid_evaluation/output/queuing-qcam1/baseline-default
```

The model is not trained or modified. The command extracts embeddings, searches
the gallery, applies the fixed threshold, and writes the baseline reports.
No calibration split is required without `--calibrate`. A single-camera result
is a useful workflow/within-camera baseline, not evidence of cross-camera accuracy.

## 7. Inspect the Baseline and Compare Another Model

Open `tools/reid_evaluation/output/queuing-qcam1/baseline-default/scorecard.md` for
the summary. Use `predictions.csv` to investigate wrong matches/rejections and
`report.json` for complete model hashes, preprocessing, runtime, and denominators.

Keep the reviewed crops, identities, and exclusions unchanged. Supply a replacement
IR XML/BIN pair and run it against the same manifest:

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate \
  --manifest tools/reid_evaluation/output/queuing-qcam1/manifest.json \
  --model /absolute/path/to/candidate.xml \
  --model-name candidate --model-version checkpoint-or-release \
  --allow-same-camera --metric COSINE --threshold 0.5 \
  --baseline tools/reid_evaluation/output/queuing-qcam1/baseline-default/report.json \
  --output tools/reid_evaluation/output/queuing-qcam1/candidate-fixed
```

The candidate path is the one placeholder here: replace it with your exported
model's real host path. Set its required preprocessing and metric explicitly;
the defaults are not correct for every model. Comparing both models at `0.5`
answers how they behave at that fixed cosine operating point, not which has the
best independently calibrated performance. For model selection, use the separate
calibration procedure below when you have enough labeled identities.

The candidate `report.json` includes baseline metric deltas after verifying the
dataset/exclusion protocol matches. Positive deltas are good for Rank-1/mAP, but
negative deltas are good for error rates. New embedding lengths are supported;
do not mix embeddings from different models in one run.

## Troubleshooting

| Symptom                                       | Action                                                                                                                                                        |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.venv/bin/python: No such file or directory` | Run step 1 from the repository root.                                                                                                                          |
| Missing video, model, or manifest             | Check the exact host paths; Docker paths are not automatically host paths. Run model setup/export/review steps first.                                         |
| Output already exists                         | Choose a new output directory or manifest filename. The tools deliberately do not overwrite results.                                                          |
| No crops found                                | Inspect the video, confirm the detector's SSD format/person label, and review `--confidence`/`--minimum-area`; do not lower filters just to improve accuracy. |
| Crop needs an identity/split                  | Fill in the retained CSV row or set `include=no`.                                                                                                             |
| No eligible test queries                      | With one camera, use `--allow-same-camera`; otherwise ensure known queries have cross-camera gallery references.                                              |
| Calibration/test identities must be disjoint  | Reassign people to separate query splits, or omit calibration for an initial fixed-threshold run.                                                             |
| No unknown test identities                    | Add real people absent from the gallery to measure false accepts. Unknown rates are otherwise unmeasured.                                                     |

## Reference: Manually Prepared Evaluation Data

## Label the Evaluation Data

Provide a JSON manifest. Image paths are relative to the manifest, or absolute.
Each image must already be a person crop: run the same detector/crop selection
for every candidate, or prepare manually verified crops.

```json
{
  "dataset": { "name": "retail-labeled-v1" },
  "samples": [
    {
      "id": "gallery-a",
      "identity": "person-a",
      "camera": "cam-1",
      "split": "gallery",
      "image": "crops/gallery-a.png"
    },
    {
      "id": "gallery-b",
      "identity": "person-b",
      "camera": "cam-1",
      "split": "gallery",
      "image": "crops/gallery-b.png"
    },
    {
      "id": "cal-a",
      "identity": "person-a",
      "camera": "cam-2",
      "split": "calibration",
      "image": "crops/cal-a.png"
    },
    {
      "id": "cal-unknown",
      "identity": "unknown-cal",
      "camera": "cam-2",
      "split": "calibration",
      "image": "crops/cal-unknown.png"
    },
    {
      "id": "test-b",
      "identity": "person-b",
      "camera": "cam-3",
      "split": "test",
      "image": "crops/test-b.png"
    },
    {
      "id": "test-unknown",
      "identity": "unknown-test",
      "camera": "cam-3",
      "split": "test",
      "image": "crops/test-unknown.png"
    }
  ]
}
```

- IDs are unique sample identifiers, not person labels.
- `identity` is a human-verified person label, consistent across cameras/visits.
- `gallery` contains reference observations for known people. Unknown query
  identities must have no gallery entries.
- Calibration/test query identities must be disjoint when using `--calibrate`;
  their known identities may both have references in the gallery.
- All same-camera gallery entries are excluded by default. `--allow-same-camera`
  relaxes this; an optional `track_id` still excludes same-camera/same-track pairs.
- Use different capture sessions/tracklets where possible. Do not use adjacent
  frames as independent evidence. Exact image hashes crossing splits are rejected;
  that does not detect near-duplicate frames, which remain your dataset responsibility.
- A known query without an eligible positive after exclusions is reported as
  skipped, not incorrectly treated as an unknown person.

The tiny example above explains the format, not a sufficient evaluation set.
Include diverse viewpoints, occlusion, lighting, distractors, and enough unknown
queries to support the intended false-accept operating point. Camera IDs and
report identities should be pseudonymous; reports contain labels and embeddings.

## Establish the Default-Model Baseline

Use the installed OpenVINO IR `.xml` and adjacent `.bin`, for example under the
models volume's `omz/person-reidentification-retail-0277/FP32/` directory. Mount
or copy these read-only to a host-accessible path; this CLI does not manage Docker
or automatically download a model or dataset.

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate \
  --manifest /data/reid/manifest.json \
  --model /models/person-reidentification-retail-0277.xml \
  --model-version omz-0277-fp32 \
  --metric COSINE --threshold 0.5 \
  --output /data/reid/results/omz-0277-fixed
```

Cosine and `0.5` match the current Controller configuration at tool introduction.
They are a fixed operating point, not proof of an optimal threshold. The default
image preprocessing is BGR/NCHW, resized to the model's static input shape using
Pillow bilinear, float pixels in 0-255, no additional mean/std. Verify this against
the exported model. It is not a claim of pixel-identical DLStreamer/OpenCV resize.

Override candidate preprocessing with `--color-order RGB`, `--layout NHWC`,
`--pixel-scale 0.00392156862745`, `--mean R G B`, and `--std R G B` as required.
The formula is `(pixel * pixel_scale - mean) / std`, after channel ordering.
Use `--output-name` for multi-output models. Only static, batch-one,
three-channel OpenVINO IR image inputs are supported. Compilation and warmup
are excluded from inference timings; measured inference is synchronous, serial,
and includes OpenVINO request overhead, not detector or MQTT latency.

## Calibrate and Compare

Choose a threshold on calibration queries only, then freeze it for final tests:

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate \
  --manifest /data/reid/manifest.json \
  --model /models/person-reidentification-retail-0277.xml \
  --calibrate --target-false-accept-rate 0.01 \
  --output /data/reid/results/omz-0277-calibrated
```

Calibration requires both eligible known and unknown queries. It maximizes
correct known-identity acceptance within the observed unknown false-accept
budget, breaking ties against misidentifications/false accepts. It fails if the
requested budget is impossible. A small calibration set cannot substantiate a
low population false-accept rate; the scorecard records denominators and warnings.

Run a replacement against the same manifest and protocol:

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate \
  --manifest /data/reid/manifest.json --model /models/candidate.xml \
  --model-name candidate --model-version checkpoint-hash-or-release \
  --calibrate --target-false-accept-rate 0.01 \
  --baseline /data/reid/results/omz-0277-calibrated/report.json \
  --output /data/reid/results/candidate-calibrated
```

Set candidate-specific preprocessing and metric explicitly. `L2` here means
Euclidean distance, accepted at `distance <= threshold`; cosine accepts at
`similarity >= threshold` and L2-normalizes vectors before scoring. Do not reuse
thresholds from squared-distance backends. The comparison checks sample labels,
IDs, camera/track exclusions, and available source-image hashes, independent of
model embedding length. Keep model embeddings in separate runs; never mix them
in a single gallery. Cached-manifest model metadata remains user-supplied.

## Reports and Metric Definitions

Each new output directory contains:

- `report.json`: model/version, XML/BIN SHA-256, preprocessing, dataset/protocol
  hashes, configured and calibrated operating points, metrics, warnings, runtime.
- `scorecard.csv` and `scorecard.md`: model comparison summaries.
- `predictions.csv`: evaluated-query candidate, score, acceptance and identity.
- `threshold_sweep.csv`: calibration operating points; empty without calibration.
- `embeddings.json`: reusable vectors plus labels/model metadata. It can be passed
  back as `--manifest` without `--model`; inference timing then remains unmeasured.

Rank-1 and mAP are computed over eligible known queries before thresholding.
AP averages precision at each relevant gallery rank; ties use stable sample-ID
ordering. Unknowns do not contribute to retrieval accuracy.

- `true_identification_rate`: correct accepted known queries / known queries.
- `known_misidentification_rate`: wrong accepted known queries / known queries.
- `known_rejection_rate`: rejected known queries / known queries.
- `false_negative_identification_rate`: rejected or misidentified known queries /
  known queries (one minus true identification rate).
- `unknown_false_accept_rate`: accepted unknown queries / unknown queries, using
  each query's top gallery candidate. This is identification-level, not pairwise FMR.

Reports do not overwrite existing run directories. Missing denominators/timing
are `null`, never fabricated zeros. Peak RSS is process-wide host memory, not GPU
memory or a model-only allocation measurement. CPU time includes the complete
evaluation; inference/preprocessing have separate timing distributions.

**Not measured:** unique-person-count error, SceneScape's multi-frame voting,
enrollment/TTL behavior, GPU utilization, or end-to-end decision latency. Those
require labeled temporal replay through Tracker/ReID/Analytics, and can build on
the existing [tracker evaluation harness](../tracker/evaluation/README.md).

## Smoke Check and Tests

```bash
tools/reid_evaluation/.venv/bin/python -m tools.reid_evaluation.evaluate \
  --manifest tools/reid_evaluation/examples/smoke.json --calibrate \
  --output /tmp/reid-evaluation-smoke

PYTHONPATH=. tests/.venv/bin/python -m pytest -q \
  tools/reid_evaluation/tests
```

The bundled vectors are synthetic. Their reports are explicitly marked as smoke
data, not baseline accuracy for the default or any other trained model. The
OpenVINO test uses a generated pooling model and runs when OpenVINO/Pillow are
installed; it tests extraction mechanics, not ReID quality. No live deployment,
credentials, vector database, or external dataset is required for unit tests.
