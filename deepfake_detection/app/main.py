import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.config import settings
from app.model import XceptionDeepfakeClassifier
from app.video import VideoProcessingError, is_supported_video, sample_video_frames


app = FastAPI(title="Unleash Deepfake Detection API")
classifier = XceptionDeepfakeClassifier(settings)


@app.post("/deepfake/predict")
async def predict_deepfake(video: UploadFile = File(...)) -> dict[str, object]:
    if not video.filename or not is_supported_video(video.filename):
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format. Use one of: avi, mkv, mov, mp4, webm.",
        )

    suffix = os.path.splitext(video.filename)[1].lower()
    temp_path = ""

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            while chunk := await video.read(1024 * 1024):
                temp_file.write(chunk)

        frames = sample_video_frames(temp_path, settings.max_sampled_frames)
        try:
            prediction, confidence, frame_probabilities = classifier.predict_video(frames)
        except Exception as exc:
            return detector_error_response(str(exc), processed_frames=len(frames))

        fake_probability = confidence if prediction == "FAKE" else 1.0 - confidence
        real_score = 1.0 - fake_probability
        passed = prediction == "REAL"

        return {
            "score": round(real_score, 4),
            "passed": passed,
            "reason": f"Video classified as {prediction} from {len(frame_probabilities)} sampled frames.",
            "error": None,
            "prediction": prediction,
            "confidence": round(confidence, 4),
            "processed_frames": len(frame_probabilities),
            "fake_probability": round(fake_probability, 4),
        }
    except VideoProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await video.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def detector_error_response(error: str, processed_frames: int | None = None) -> dict[str, object]:
    return {
        "score": None,
        "passed": False,
        "reason": "Deepfake detector could not produce a score.",
        "error": error,
        "prediction": None,
        "confidence": None,
        "processed_frames": processed_frames,
        "fake_probability": None,
    }
