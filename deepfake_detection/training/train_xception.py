import argparse
import math
import random
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
CLASS_TO_INDEX = {"real": 0, "fake": 1}
FAKE_CLASS_INDEX = 1
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class MediaItem:
    name: str
    class_name: str
    media_type: str
    source_ids: tuple[str, ...]
    path: Path | None = None
    zip_member: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Unleash Xception deepfake classifier.")
    parser.add_argument("--dataset-zip", help="Path to a ZIP containing real/fake images or FaceForensics videos.")
    parser.add_argument("--dataset-path", help="Path to an extracted dataset folder.")
    parser.add_argument("--work-dir", default="data/unleash_train_subset", help="Where sampled frames/images are written.")
    parser.add_argument("--checkpoint-output", default="checkpoints/xception_deepfake_best.pth")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--image-size", type=int, default=299)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--real-total", type=int, default=2000)
    parser.add_argument("--fake-total", type=int, default=2000)
    parser.add_argument("--train-per-class", type=int, default=1600)
    parser.add_argument("--val-per-class", type=int, default=200)
    parser.add_argument("--test-per-class", type=int, default=200)
    parser.add_argument("--frames-per-video", type=int, default=4)
    parser.add_argument("--max-source-groups", type=int, help="Limit source-ID groups for video datasets.")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--resume", action="store_true", help="Resume model/optimizer state from checkpoint output.")
    parser.add_argument("--no-pretrained", action="store_true", help="Disable ImageNet-pretrained initialization.")
    parser.add_argument("--overwrite-extracted", action="store_true", help="Recreate the work-dir before extraction.")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect dataset and split without extracting/training.")
    parser.add_argument("--prepare-only", action="store_true", help="Extract/copy frames but do not train.")
    parser.add_argument("--smoke-test", action="store_true", help="Use tiny counts for a quick one-epoch check.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if bool(args.dataset_zip) == bool(args.dataset_path):
        raise ValueError("Provide exactly one of --dataset-zip or --dataset-path.")

    if args.smoke_test:
        args.real_total = 8
        args.fake_total = 8
        args.train_per_class = 4
        args.val_per_class = 2
        args.test_per_class = 2
        args.epochs = 1
        args.batch_size = min(args.batch_size, 2)
        args.frames_per_video = min(args.frames_per_video, 1)
        args.max_source_groups = args.max_source_groups or 3

    validate_args(args)
    source_path = Path(args.dataset_zip or args.dataset_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Dataset source not found: {source_path}")

    media_items = inspect_dataset(source_path, is_zip=bool(args.dataset_zip))
    split_items, split_strategy = build_split(media_items, args)
    print_dataset_summary(media_items, split_items, split_strategy)

    if args.inspect_only:
        return

    prepare_work_dir(source_path, split_items, Path(args.work_dir), bool(args.dataset_zip), args)

    if args.prepare_only:
        print(f"Prepared dataset at: {Path(args.work_dir)}")
        return

    run_training(args, Path(args.work_dir), split_strategy)


def validate_args(args: argparse.Namespace) -> None:
    expected_per_class = args.train_per_class + args.val_per_class + args.test_per_class
    if args.real_total != expected_per_class or args.fake_total != expected_per_class:
        raise ValueError("Per-class train/val/test counts must add up to the requested class totals.")

    ratio_sum = args.train_ratio + args.val_ratio + args.test_ratio
    if not math.isclose(ratio_sum, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Video split ratios must add up to 1.0.")

    if args.frames_per_video < 1:
        raise ValueError("--frames-per-video must be at least 1.")


def inspect_dataset(source_path: Path, is_zip: bool) -> list[MediaItem]:
    if is_zip:
        return inspect_zip(source_path)
    return inspect_directory(source_path)


def inspect_zip(dataset_zip: Path) -> list[MediaItem]:
    items = []
    with zipfile.ZipFile(dataset_zip) as archive:
        for member in archive.namelist():
            if member.endswith("/"):
                continue

            path = PurePosixPath(member)
            media_type = media_type_for_suffix(path.suffix)
            if media_type is None:
                continue

            item = make_media_item(path, media_type, zip_member=member)
            if item:
                items.append(item)

    validate_detected_items(items)
    return items


def inspect_directory(dataset_path: Path) -> list[MediaItem]:
    items = []
    for file_path in dataset_path.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = PurePosixPath(file_path.relative_to(dataset_path).as_posix())
        media_type = media_type_for_suffix(file_path.suffix)
        if media_type is None:
            continue

        item = make_media_item(relative_path, media_type, path=file_path)
        if item:
            items.append(item)

    validate_detected_items(items)
    return items


def media_type_for_suffix(suffix: str) -> str | None:
    lower_suffix = suffix.lower()
    if lower_suffix in IMAGE_EXTENSIONS:
        return "image"
    if lower_suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def make_media_item(
    relative_path: PurePosixPath,
    media_type: str,
    path: Path | None = None,
    zip_member: str | None = None,
) -> MediaItem | None:
    parts = tuple(part.lower() for part in relative_path.parts)
    class_name = class_name_from_parts(parts)
    if class_name is None:
        return None

    source_ids = infer_source_ids(relative_path, class_name, media_type)
    if not source_ids:
        raise ValueError(f"Could not infer source ID from: {relative_path}")

    return MediaItem(
        name=relative_path.as_posix(),
        class_name=class_name,
        media_type=media_type,
        source_ids=source_ids,
        path=path,
        zip_member=zip_member,
    )


def class_name_from_parts(parts: tuple[str, ...]) -> str | None:
    if "original_sequences" in parts:
        return "real"
    if "manipulated_sequences" in parts and "deepfakes" in parts:
        return "fake"
    if "real" in parts:
        return "real"
    if "fake" in parts:
        return "fake"
    return None


def infer_source_ids(relative_path: PurePosixPath, class_name: str, media_type: str) -> tuple[str, ...]:
    stem_parts = tuple(part for part in relative_path.stem.split("_") if part)

    if media_type == "video":
        if class_name == "real" and len(stem_parts) == 1:
            return stem_parts
        if class_name == "fake" and len(stem_parts) >= 2:
            return stem_parts[:2]

    if media_type == "image":
        if class_name == "real" and len(stem_parts) >= 1:
            return (stem_parts[0],)
        if class_name == "fake" and len(stem_parts) >= 2:
            return stem_parts[:2]

    return ()


def validate_detected_items(items: list[MediaItem]) -> None:
    if not items:
        raise ValueError("No supported images or videos were found.")

    media_types = {item.media_type for item in items}
    if len(media_types) > 1:
        raise ValueError(f"Dataset mixes media types {sorted(media_types)}. Use one media type per run.")

    counts = Counter(item.class_name for item in items)
    for class_name in ("real", "fake"):
        if counts[class_name] == 0:
            raise ValueError(f"No {class_name} samples were detected.")


def build_split(items: list[MediaItem], args: argparse.Namespace) -> tuple[dict[str, list[MediaItem]], str]:
    media_type = items[0].media_type
    if media_type == "video":
        return build_video_split(items, args), "source-video grouped"
    return build_image_split(items, args), "filename-derived source-video grouped"


def build_image_split(items: list[MediaItem], args: argparse.Namespace) -> dict[str, list[MediaItem]]:
    rng = random.Random(args.seed)
    split_items = {"train": [], "val": [], "test": []}
    targets = {
        "train": args.train_per_class,
        "val": args.val_per_class,
        "test": args.test_per_class,
    }

    for class_name in ("real", "fake"):
        class_items = sorted([item for item in items if item.class_name == class_name], key=lambda item: item.name)
        rng.shuffle(class_items)
        total_needed = sum(targets.values())
        if len(class_items) < total_needed:
            raise ValueError(f"Not enough {class_name} images to create requested split.")

        cursor = 0
        for split_name, target_count in targets.items():
            split_items[split_name].extend(class_items[cursor:cursor + target_count])
            cursor += target_count

    return split_items


def build_video_split(items: list[MediaItem], args: argparse.Namespace) -> dict[str, list[MediaItem]]:
    rng = random.Random(args.seed)
    groups = source_groups(items)
    group_items = sorted(groups.items(), key=lambda item: item[0])
    rng.shuffle(group_items)

    if args.max_source_groups:
        if args.max_source_groups < 3:
            raise ValueError("--max-source-groups must be at least 3 so train/val/test can all receive data.")
        group_items = group_items[:args.max_source_groups]

    total_groups = len(group_items)
    if total_groups < 3:
        raise ValueError("At least 3 source groups are required for train/val/test.")

    train_count = max(1, int(total_groups * args.train_ratio))
    val_count = max(1, int(total_groups * args.val_ratio))
    test_count = total_groups - train_count - val_count
    if test_count < 1:
        test_count = 1
        train_count = max(1, total_groups - val_count - test_count)

    split_groups = {
        "train": group_items[:train_count],
        "val": group_items[train_count:train_count + val_count],
        "test": group_items[train_count + val_count:],
    }

    split_items = {
        split_name: [item for _, group_members in members for item in group_members]
        for split_name, members in split_groups.items()
    }
    validate_video_split(split_items)
    return split_items


def source_groups(items: list[MediaItem]) -> dict[str, list[MediaItem]]:
    parent: dict[str, str] = {}

    def find(source_id: str) -> str:
        parent.setdefault(source_id, source_id)
        if parent[source_id] != source_id:
            parent[source_id] = find(parent[source_id])
        return parent[source_id]

    def union(first: str, second: str) -> None:
        parent[find(second)] = find(first)

    for item in items:
        for source_id in item.source_ids:
            parent.setdefault(source_id, source_id)
        for source_id in item.source_ids[1:]:
            union(item.source_ids[0], source_id)

    groups: dict[str, list[MediaItem]] = defaultdict(list)
    for item in items:
        groups[find(item.source_ids[0])].append(item)
    return groups


def validate_video_split(split_items: dict[str, list[MediaItem]]) -> None:
    seen_source_ids: dict[str, str] = {}
    for split_name, items in split_items.items():
        counts = Counter(item.class_name for item in items)
        if counts["real"] == 0 or counts["fake"] == 0:
            raise ValueError(f"{split_name} split does not contain both real and fake videos.")

        for item in items:
            for source_id in item.source_ids:
                previous_split = seen_source_ids.get(source_id)
                if previous_split and previous_split != split_name:
                    raise ValueError(f"Source ID {source_id} appears in both {previous_split} and {split_name}.")
                seen_source_ids[source_id] = split_name


def print_dataset_summary(
    items: list[MediaItem],
    split_items: dict[str, list[MediaItem]],
    split_strategy: str,
) -> None:
    media_type = items[0].media_type
    total_counts = Counter(item.class_name for item in items)
    print(f"Dataset media type: {media_type}")
    print("Dataset samples found:")
    for class_name in ("real", "fake"):
        print(f"  {class_name}: {total_counts[class_name]}")

    print(f"Split strategy: {split_strategy}")
    for split_name in ("train", "val", "test"):
        counts = Counter(item.class_name for item in split_items[split_name])
        print(f"  {split_name}: real={counts['real']} fake={counts['fake']} total={len(split_items[split_name])}")

    if media_type == "video":
        print("Frames are extracted after the split, so source IDs do not cross train/val/test.")


def prepare_work_dir(
    source_path: Path,
    split_items: dict[str, list[MediaItem]],
    work_dir: Path,
    is_zip: bool,
    args: argparse.Namespace,
) -> None:
    if work_dir.exists() and args.overwrite_extracted:
        shutil.rmtree(work_dir)

    work_dir.mkdir(parents=True, exist_ok=True)
    first_split = next(split for split in split_items.values() if split)
    media_type = first_split[0].media_type
    if media_type == "image":
        prepare_image_split(source_path, split_items, work_dir, is_zip)
    else:
        prepare_video_split(source_path, split_items, work_dir, is_zip, args.frames_per_video)


def prepare_image_split(
    source_path: Path,
    split_items: dict[str, list[MediaItem]],
    work_dir: Path,
    is_zip: bool,
) -> None:
    archive = zipfile.ZipFile(source_path) if is_zip else None
    try:
        for split_name, items in split_items.items():
            for item in items:
                output_path = work_dir / split_name / item.class_name / PurePosixPath(item.name).name
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if output_path.exists():
                    continue
                if archive:
                    with archive.open(item.zip_member or item.name) as source, output_path.open("wb") as target:
                        shutil.copyfileobj(source, target)
                else:
                    if item.path is None:
                        raise ValueError(f"Missing image path for {item.name}")
                    shutil.copy2(item.path, output_path)
    finally:
        if archive:
            archive.close()


def prepare_video_split(
    source_path: Path,
    split_items: dict[str, list[MediaItem]],
    work_dir: Path,
    is_zip: bool,
    frames_per_video: int,
) -> None:
    archive = zipfile.ZipFile(source_path) if is_zip else None
    try:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            for split_name, items in split_items.items():
                for item in items:
                    output_dir = work_dir / split_name / item.class_name
                    output_dir.mkdir(parents=True, exist_ok=True)

                    if archive:
                        video_path = temp_dir / PurePosixPath(item.name).name
                        with archive.open(item.zip_member or item.name) as source, video_path.open("wb") as target:
                            shutil.copyfileobj(source, target)
                    else:
                        if item.path is None:
                            raise ValueError(f"Missing video path for {item.name}")
                        video_path = item.path

                    extract_frames_from_video(video_path, output_dir, item.name, frames_per_video)
    finally:
        if archive:
            archive.close()


def extract_frames_from_video(video_path: Path, output_dir: Path, item_name: str, frames_per_video: int) -> None:
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {item_name}")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count <= 0:
        capture.release()
        raise ValueError(f"Video has no readable frame count: {item_name}")

    total_frames = min(frames_per_video, frame_count)
    frame_indexes = sorted(set(int(index) for index in linspace_indexes(frame_count, total_frames)))
    stem = safe_stem(item_name)

    saved = 0
    for frame_index in frame_indexes:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, frame = capture.read()
        if not success or frame is None:
            continue
        output_path = output_dir / f"{stem}_frame_{frame_index:05d}.png"
        cv2.imwrite(str(output_path), frame)
        saved += 1

    capture.release()
    if saved == 0:
        raise ValueError(f"No frames could be extracted from: {item_name}")


def linspace_indexes(frame_count: int, total_frames: int) -> list[int]:
    if total_frames <= 1:
        return [frame_count // 2]
    step = (frame_count - 1) / (total_frames - 1)
    return [round(index * step) for index in range(total_frames)]


def safe_stem(item_name: str) -> str:
    path = PurePosixPath(item_name)
    class_prefix = "fake" if "manipulated_sequences" in [part.lower() for part in path.parts] else "real"
    return f"{class_prefix}_{path.stem}"


def run_training(args: argparse.Namespace, work_dir: Path, split_strategy: str) -> None:
    import cv2
    import numpy as np
    import timm
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset

    seed_everything(args.seed, torch, np)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    print(f"Seed: {args.seed}")

    class ImageDataset(Dataset):
        def __init__(self, split_dir: Path, image_size: int, training: bool) -> None:
            self.image_size = image_size
            self.training = training
            self.items = []
            for class_name, label in CLASS_TO_INDEX.items():
                class_dir = split_dir / class_name
                image_paths = sorted(class_dir.glob("*")) if class_dir.exists() else []
                for image_path in image_paths:
                    if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                        self.items.append((image_path, label))
            if not self.items:
                raise ValueError(f"No images found in {split_dir}")

        def __len__(self) -> int:
            return len(self.items)

        def __getitem__(self, index: int):
            image_path, label = self.items[index]
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Could not read image: {image_path}")
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image = augment_image(image) if self.training else image
            image = cv2.resize(image, (self.image_size, self.image_size), interpolation=cv2.INTER_AREA)
            image = image.astype("float32") / 255.0
            image = (image - np.array(IMAGENET_MEAN, dtype="float32")) / np.array(IMAGENET_STD, dtype="float32")
            tensor = torch.from_numpy(image).permute(2, 0, 1).float()
            return tensor, torch.tensor(label, dtype=torch.long)

    train_dataset = ImageDataset(work_dir / "train", args.image_size, training=True)
    val_dataset = ImageDataset(work_dir / "val", args.image_size, training=False)
    test_dataset = ImageDataset(work_dir / "test", args.image_size, training=False)

    print(f"Prepared frames/images: train={len(train_dataset)} val={len(val_dataset)} test={len(test_dataset)}")

    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        generator=generator,
    )
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)

    pretrained = not args.no_pretrained
    try:
        model = timm.create_model("xception", pretrained=pretrained, num_classes=2)
    except Exception as exc:
        if not pretrained:
            raise
        print(f"Could not initialize pretrained Xception ({exc}). Falling back to pretrained=False.")
        model = timm.create_model("xception", pretrained=False, num_classes=2)

    model = model.to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    start_epoch = 1
    checkpoint_path = Path(args.checkpoint_output)

    if args.resume and checkpoint_path.exists():
        start_epoch, best_val_accuracy = load_training_checkpoint(model, optimizer, checkpoint_path, device)
        start_epoch += 1
        print(f"Resumed from {checkpoint_path} at epoch {start_epoch}")
    else:
        best_val_accuracy = -math.inf

    verify_one_batch(model, train_loader, device)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(start_epoch, args.epochs + 1):
        train_loss, train_accuracy = run_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_accuracy = evaluate(model, val_loader, criterion, device)[:2]
        print(
            f"Epoch {epoch}/{args.epochs} "
            f"train_loss={train_loss:.4f} train_acc={train_accuracy:.4f} "
            f"val_loss={val_loss:.4f} val_acc={val_accuracy:.4f}"
        )

        if val_accuracy > best_val_accuracy:
            best_val_accuracy = val_accuracy
            save_checkpoint(model, optimizer, checkpoint_path, args, split_strategy, val_accuracy, epoch)
            verify_checkpoint_load(checkpoint_path, device)
            print(f"Saved best checkpoint: {checkpoint_path}")

    verify_checkpoint_load(checkpoint_path, device)
    model.load_state_dict(load_state_dict(checkpoint_path, device), strict=True)
    test_loss, test_accuracy, metrics = evaluate(model, test_loader, criterion, device)
    print(f"Test loss: {test_loss:.4f}")
    print(f"Test accuracy: {test_accuracy:.4f}")
    print(f"Confusion matrix [[real_as_real, real_as_fake], [fake_as_real, fake_as_fake]]: {metrics['confusion_matrix']}")
    print(f"REAL precision={metrics['real_precision']:.4f} recall={metrics['real_recall']:.4f}")
    print(f"FAKE precision={metrics['fake_precision']:.4f} recall={metrics['fake_recall']:.4f}")


def seed_everything(seed: int, torch_module, np_module) -> None:
    random.seed(seed)
    np_module.random.seed(seed)
    torch_module.manual_seed(seed)
    if torch_module.cuda.is_available():
        torch_module.cuda.manual_seed_all(seed)


def augment_image(image):
    import cv2
    import numpy as np

    if random.random() < 0.5:
        image = cv2.flip(image, 1)

    if random.random() < 0.4:
        alpha = random.uniform(0.9, 1.1)
        beta = random.uniform(-8, 8)
        image = np.clip(image.astype("float32") * alpha + beta, 0, 255).astype("uint8")

    if random.random() < 0.25:
        height, width = image.shape[:2]
        angle = random.uniform(-5, 5)
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        image = cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REFLECT_101)

    return image


def verify_one_batch(model, data_loader, device) -> None:
    import torch

    images, _ = next(iter(data_loader))
    images = images.to(device)
    with torch.no_grad():
        logits = model(images)
    if tuple(logits.shape) != (images.shape[0], 2):
        raise RuntimeError(f"Expected model output shape [batch_size, 2], got {tuple(logits.shape)}")
    print(f"One-batch model check passed. Output shape: {tuple(logits.shape)}")


def run_epoch(model, data_loader, criterion, optimizer, device) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in data_loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * labels.size(0)
        correct += (logits.argmax(dim=1) == labels).sum().item()
        total += labels.size(0)

    return total_loss / total, correct / total


def evaluate(model, data_loader, criterion, device) -> tuple[float, float, dict[str, object]]:
    import torch

    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    confusion = [[0, 0], [0, 0]]

    with torch.no_grad():
        for images, labels in data_loader:
            images = images.to(device)
            labels = labels.to(device)
            logits = model(images)
            loss = criterion(logits, labels)
            predictions = logits.argmax(dim=1)

            total_loss += loss.item() * labels.size(0)
            correct += (predictions == labels).sum().item()
            total += labels.size(0)

            for label, prediction in zip(labels.cpu().tolist(), predictions.cpu().tolist()):
                confusion[label][prediction] += 1

    metrics = classification_metrics(confusion)
    return total_loss / total, correct / total, metrics


def classification_metrics(confusion: list[list[int]]) -> dict[str, object]:
    real_precision = safe_divide(confusion[0][0], confusion[0][0] + confusion[1][0])
    real_recall = safe_divide(confusion[0][0], confusion[0][0] + confusion[0][1])
    fake_precision = safe_divide(confusion[1][1], confusion[1][1] + confusion[0][1])
    fake_recall = safe_divide(confusion[1][1], confusion[1][1] + confusion[1][0])
    return {
        "confusion_matrix": confusion,
        "real_precision": real_precision,
        "real_recall": real_recall,
        "fake_precision": fake_precision,
        "fake_recall": fake_recall,
    }


def safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def save_checkpoint(
    model,
    optimizer,
    checkpoint_path: Path,
    args: argparse.Namespace,
    split_strategy: str,
    val_accuracy: float,
    epoch: int,
) -> None:
    import torch

    torch.save(
        {
            "state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "epoch": epoch,
            "model_name": "xception",
            "num_classes": 2,
            "class_to_idx": CLASS_TO_INDEX,
            "fake_class_index": FAKE_CLASS_INDEX,
            "image_size": args.image_size,
            "imagenet_mean": IMAGENET_MEAN,
            "imagenet_std": IMAGENET_STD,
            "split_strategy": split_strategy,
            "best_val_accuracy": val_accuracy,
        },
        checkpoint_path,
    )


def load_training_checkpoint(model, optimizer, checkpoint_path: Path, device) -> tuple[int, float]:
    import torch

    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    optimizer_state = checkpoint.get("optimizer_state_dict")
    if optimizer_state:
        optimizer.load_state_dict(optimizer_state)
    return int(checkpoint.get("epoch", 0)), float(checkpoint.get("best_val_accuracy", -math.inf))


def load_state_dict(checkpoint_path: Path, device):
    import torch

    checkpoint = torch.load(checkpoint_path, map_location=device)
    return checkpoint["state_dict"]


def verify_checkpoint_load(checkpoint_path: Path, device) -> None:
    import timm

    model = timm.create_model("xception", pretrained=False, num_classes=2)
    model.load_state_dict(load_state_dict(checkpoint_path, device), strict=True)


if __name__ == "__main__":
    main()
