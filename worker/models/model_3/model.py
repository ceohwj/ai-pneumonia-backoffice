from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
import torch
from torch import Tensor, nn
from torch.nn import functional as F
from torchvision import models, transforms


MODEL_DIR = Path(__file__).resolve().parent
CHECKPOINT_DIR = MODEL_DIR / "checkpoints"
CONFIG_PATH = MODEL_DIR / "config.json"

IMAGE_SIZE = 224
AI_MODEL_NAME = "jihye_resnet18_simplecnn_densenet121_v1"
HEATMAP_MODEL_NAME = "model_3_resnet18_gradcam"


class SimpleChestCNN(nn.Module):
    
    def __init__(self, num_classes: int = 2) -> None:
        super().__init__()

        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )

        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(256, num_classes),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        features = self.features(inputs)
        return self.classifier(features)


def build_resnet18() -> nn.Module:
    """2개 클래스를 출력하는 ResNet18 구조를 만든다."""

    model = models.resnet18(weights=None)
    input_features = model.fc.in_features
    model.fc = nn.Linear(input_features, 2)
    return model


def build_densenet121() -> nn.Module:
    """2개 클래스를 출력하는 DenseNet121 구조를 만든다."""

    model = models.densenet121(weights=None)
    input_features = model.classifier.in_features
    model.classifier = nn.Linear(input_features, 2)
    return model


def read_config() -> dict:
    """Kaggle 최종 앙상블 설정을 읽고 필수 항목을 확인한다."""

    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"model_3 설정 파일을 찾을 수 없습니다: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = json.load(config_file)

    if "threshold" not in config:
        raise ValueError("model_3 설정에 threshold가 없습니다.")

    if not isinstance(config.get("models"), dict):
        raise ValueError("model_3 설정에 models가 없습니다.")

    required_weights = {
        "resnet_tta_weight_inside_2model",
        "simplecnn_weight_inside_2model",
        "densenet_weight",
        "previous_2model_weight",
    }

    missing_weights = required_weights - set(config["models"])

    if missing_weights:
        missing_names = ", ".join(sorted(missing_weights))
        raise ValueError(
            f"model_3 설정에 필요한 가중치가 없습니다: {missing_names}"
        )

    return config

def select_device() -> torch.device:
    """CUDA GPU가 있으면 사용하고, 없으면 CPU를 사용한다."""

    return torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )


def load_checkpoint(
    model: nn.Module,
    checkpoint_name: str,
    device: torch.device,
) -> nn.Module:
    """체크포인트를 안전하게 읽어 모델 구조에 적용한다."""

    checkpoint_path = CHECKPOINT_DIR / checkpoint_name

    if not checkpoint_path.is_file():
        raise FileNotFoundError(
            f"model_3 체크포인트를 찾을 수 없습니다: "
            f"{checkpoint_path}"
        )

    state_dict = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=True,
    )

    model.load_state_dict(state_dict, strict=True)
    model.to(device)
    model.eval()

    return model

"""ResNet18, SimpleCNN, DenseNet121 3모델 앙상블."""

class Model3Ensemble: 
    def __init__(
        self,
        device: torch.device | None = None,
    ) -> None:
        config = read_config()
        config_weights = config["models"]

        self.device = device or select_device()
        self.threshold = float(config["threshold"])

        previous_weight = float(
            config_weights["previous_2model_weight"]
        )
        resnet_inside_weight = float(
            config_weights["resnet_tta_weight_inside_2model"]
        )
        simplecnn_inside_weight = float(
            config_weights["simplecnn_weight_inside_2model"]
        )
        densenet_weight = float(
            config_weights["densenet_weight"]
        )

        self.resnet_weight = (
            previous_weight * resnet_inside_weight
        )
        self.simplecnn_weight = (
            previous_weight * simplecnn_inside_weight
        )
        self.densenet_weight = densenet_weight

        total_weight = (
            self.resnet_weight
            + self.simplecnn_weight
            + self.densenet_weight
        )

        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                "model_3 앙상블 가중치의 합이 1이 아닙니다: "
                f"{total_weight}"
            )

        self.simplecnn = load_checkpoint(
            SimpleChestCNN(num_classes=2),
            "simplecnn_model.pth",
            self.device,
        )
        self.resnet = load_checkpoint(
            build_resnet18(),
            "resnet_model.pth",
            self.device,
        )
        self.densenet = load_checkpoint(
            build_densenet121(),
            "densenet121_model.pth",
            self.device,
        )

        self.transform = transforms.Compose(
            [
                transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def preprocess(self, image_path: Path) -> Tensor:
        """X-ray를 Kaggle 학습 당시 입력 형식으로 변환한다."""

        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image)
                rgb_image = image.convert("RGB")
                image_tensor = self.transform(rgb_image)
        except (OSError, ValueError) as exc:
            raise ValueError(
                "model_3에서 X-ray 이미지를 읽을 수 없습니다."
            ) from exc

        return image_tensor.unsqueeze(0).to(self.device)

    @staticmethod
    def pneumonia_probability(
        outputs: Tensor,
    ) -> Tensor:
        """2개 클래스 출력에서 PNEUMONIA 클래스 확률을 얻는다."""

        return torch.softmax(outputs, dim=1)[:, 1]

    def probability_with_tta(
        self,
        model: nn.Module,
        image_tensor: Tensor,
    ) -> Tensor:
        """원본과 좌우반전 결과의 폐렴 확률을 평균한다."""

        original_outputs = model(image_tensor)
        original_probability = self.pneumonia_probability(
            original_outputs
        )

        flipped_tensor = torch.flip(
            image_tensor,
            dims=[3],
        )
        flipped_outputs = model(flipped_tensor)
        flipped_probability = self.pneumonia_probability(
            flipped_outputs
        )

        return (
            original_probability + flipped_probability
        ) / 2

    @torch.inference_mode()
    def predict_probability(
        self,
        image_path: Path,
    ) -> float:
        """세 모델의 가중 평균 폐렴 확률을 계산한다."""

        image_tensor = self.preprocess(image_path)

        resnet_probability = self.probability_with_tta(
            self.resnet,
            image_tensor,
        )

        simplecnn_outputs = self.simplecnn(image_tensor)
        simplecnn_probability = self.pneumonia_probability(
            simplecnn_outputs
        )

        densenet_probability = self.probability_with_tta(
            self.densenet,
            image_tensor,
        )

        final_probability = (
            self.resnet_weight * resnet_probability
            + self.simplecnn_weight * simplecnn_probability
            + self.densenet_weight * densenet_probability
        )

        return float(
            final_probability.detach().cpu().item()
        )

    def create_resnet_gradcam(
        self,
        image_tensor: Tensor,
        target_class: int,
    ) -> np.ndarray:
        """대표 ResNet18이 판정 시 주목한 영역을 계산한다."""

        activations: dict[str, Tensor] = {}
        gradients: dict[str, Tensor] = {}

        def save_activation(
            module: nn.Module,
            inputs: tuple[Tensor, ...],
            output: Tensor,
        ) -> None:
            activations["value"] = output

        def save_gradient(
            module: nn.Module,
            grad_input: tuple[Tensor | None, ...],
            grad_output: tuple[Tensor | None, ...],
        ) -> None:
            gradient = grad_output[0]

            if gradient is not None:
                gradients["value"] = gradient

        target_layer = self.resnet.layer4[-1]

        forward_hook = target_layer.register_forward_hook(
            save_activation
        )
        backward_hook = target_layer.register_full_backward_hook(
            save_gradient
        )

        try:
            self.resnet.zero_grad(set_to_none=True)

            outputs = self.resnet(image_tensor)
            target_score = outputs[:, target_class].sum()
            target_score.backward()

            activation = activations["value"]
            gradient = gradients["value"]

            channel_weights = gradient.mean(
                dim=(2, 3),
                keepdim=True,
            )

            gradcam = torch.relu(
                (channel_weights * activation).sum(
                    dim=1,
                    keepdim=True,
                )
            )

            gradcam = F.interpolate(
                gradcam,
                size=(IMAGE_SIZE, IMAGE_SIZE),
                mode="bilinear",
                align_corners=False,
            )[0, 0]

            minimum = gradcam.min()
            value_range = gradcam.max() - minimum

            if float(value_range.detach().cpu().item()) > 1e-12:
                gradcam = (gradcam - minimum) / value_range
            else:
                gradcam = torch.zeros_like(gradcam)

            return gradcam.detach().cpu().numpy()

        finally:
            forward_hook.remove()
            backward_hook.remove()

    @staticmethod
    def save_gradcam_overlay(
        image_path: Path,
        gradcam: np.ndarray,
        heatmap_path: Path,
    ) -> None:
        """Grad-CAM을 원본 X-ray 위에 합성해 저장한다."""

        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image)
                rgb_image = image.convert("RGB")
                original = np.asarray(rgb_image)
        except (OSError, ValueError) as exc:
            raise ValueError(
                "Grad-CAM 원본 이미지를 읽을 수 없습니다."
            ) from exc

        height, width = original.shape[:2]

        resized_gradcam = cv2.resize(
            gradcam.astype(np.float32),
            (width, height),
            interpolation=cv2.INTER_LINEAR,
        )
        resized_gradcam = np.clip(
            resized_gradcam,
            0.0,
            1.0,
        )

        colored_heatmap = cv2.applyColorMap(
            np.uint8(resized_gradcam * 255),
            cv2.COLORMAP_JET,
        )
        colored_heatmap = cv2.cvtColor(
            colored_heatmap,
            cv2.COLOR_BGR2RGB,
        ).astype(np.float32)

        original_float = original.astype(np.float32)

        alpha = (
            resized_gradcam[:, :, np.newaxis] * 0.55
        )

        overlay = (
            original_float * (1.0 - alpha)
            + colored_heatmap * alpha
        )
        overlay = np.clip(
            overlay,
            0,
            255,
        ).astype(np.uint8)

        heatmap_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_image = Image.fromarray(overlay)
        output_image.save(
            heatmap_path,
            quality=92,
        )

    def predict(
        self,
        image_path: Path,
        heatmap_path: Path,
    ) -> dict[str, bool | float | str]:
        """폐렴 확률, 판정, Confidence와 Grad-CAM을 생성한다."""

        probability = self.predict_probability(image_path)
        is_pneumonia = probability >= self.threshold

        confidence = (
            probability
            if is_pneumonia
            else 1.0 - probability
        )

        image_tensor = self.preprocess(image_path)
        target_class = 1 if is_pneumonia else 0

        gradcam = self.create_resnet_gradcam(
            image_tensor,
            target_class,
        )

        self.save_gradcam_overlay(
            image_path,
            gradcam,
            heatmap_path,
        )

        return {
            "is_pneumonia": is_pneumonia,
            "confidence": round(confidence * 100.0, 2),
            "pneumonia_probability": round(
                probability * 100.0,
                2,
            ),
            "threshold": round(
                self.threshold * 100.0,
                2,
            ),
            "heatmap_model": HEATMAP_MODEL_NAME,
            "ai_model": AI_MODEL_NAME,
        }

@lru_cache(maxsize=1)
def get_model() -> Model3Ensemble:
    """model_3를 최초 요청 시 한 번만 메모리에 로드한다."""

    return Model3Ensemble()