## Deepfake Detection

The deepfake detection module uses an Xception-based classifier trained on FaceForensics++ to classify video content as REAL or FAKE.

### Features
- Xception-based deepfake classification
- Video frame sampling for efficient inference
- Frame-level predictions aggregated into a video-level score
- Source-video-level train/validation/test splitting to reduce data leakage
- Checkpoint saving and training resume support
- FastAPI integration for backend inference
- Graceful error handling during inference

### Model
- Architecture: Xception
- Input size: 299 × 299
- Classes:
  - `0` → REAL
  - `1` → FAKE
- Dataset: FaceForensics++

### Current Status
The training and inference pipeline has been implemented and integrated with the FastAPI backend. The current checkpoint achieves approximately 76.5% accuracy on the configured test split. Further training and evaluation can be performed to improve generalization and deepfake detection performance.

> The trained checkpoint is kept outside the Git repository due to its size.
