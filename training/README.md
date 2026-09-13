# Xception Training

Minimal training pipeline for the Unleash deepfake classifier.

Supported dataset inputs:

```text
Image ZIP:
  real/
    image.png
  fake/
    image.png

FaceForensics video ZIP/folder:
  data/original_sequences/youtube/c23/videos/*.mp4      -> REAL
  data/manipulated_sequences/Deepfakes/c23/videos/*.mp4 -> FAKE
```

Class mapping is fixed to match the FastAPI backend:

```text
0 = REAL
1 = FAKE
```

## Inspect the dataset and split

```bash
python training/train_xception.py --dataset-zip "E:\Unleash_project\FaceForensics\data.zip" --inspect-only
```

## Smoke test

Use this before a full run:

```bash
python training/train_xception.py --dataset-zip "E:\Unleash_project\FaceForensics\data.zip" --smoke-test --no-pretrained --overwrite-extracted
```

## Train

For the video dataset, choose the sample size first. This example uses 4 frames per video
and only 12 source-ID groups so it stays small:

```bash
python training/train_xception.py ^
  --dataset-zip "E:\Unleash_project\FaceForensics\data.zip" ^
  --checkpoint-output "checkpoints\xception_deepfake_best.pth" ^
  --max-source-groups 12 ^
  --frames-per-video 4 ^
  --epochs 3 ^
  --batch-size 16 ^
  --learning-rate 0.0001 ^
  --overwrite-extracted
```

For the older image ZIP workflow, defaults still use 2,000 REAL and 2,000 FAKE images:

```text
train: 1,600 REAL + 1,600 FAKE
val:     200 REAL +   200 FAKE
test:    200 REAL +   200 FAKE
```

The saved checkpoint stores `state_dict`, so it is compatible with the existing
`app/model.py` backend loader. After training, run the API with:

```bash
set UNLEASH_XCEPTION_CHECKPOINT=C:\path\to\xception_deepfake_best.pth
uvicorn app.main:app --reload
```

To resume training from the same checkpoint path:

```bash
python training/train_xception.py --dataset-zip "E:\Unleash_project\FaceForensics\data.zip" --resume
```
