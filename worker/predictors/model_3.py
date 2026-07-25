from pathlib import Path

from worker.predictors.base import PredictionResult


class Model3Predictor:
    """김지혜 Kaggle 3모델 앙상블 adapter."""

    model_key = "model_3"
    experiment_name = (
        "jihye_resnet18_simplecnn_densenet121_v1"
    )
    model_version = "1.0.0"
    ai_model = experiment_name

    def predict(
        self,
        image_path: Path,
        heatmap_path: Path,
    ) -> PredictionResult:
        # 무거운 모델은 model_3가 실제 선택될 때만 로드한다.
        from worker.models.model_3.model import get_model

        result = get_model().predict(
            image_path,
            heatmap_path,
        )

        return PredictionResult(
            is_pneumonia=bool(
                result["is_pneumonia"]
            ),
            confidence=float(
                result["confidence"]
            ),
            heatmap_path=heatmap_path,
            heatmap_model=str(
                result["heatmap_model"]
            ),
            ai_model=self.ai_model,
        )