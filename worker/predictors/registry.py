from functools import lru_cache

from worker.predictors.base import PneumoniaPredictor
from worker.predictors.model_1 import Model1Predictor
from worker.predictors.model_3 import Model3Predictor


class UnsupportedModelError(ValueError):
    """등록되지 않은 모델 키가 요청된 경우."""


PREDICTOR_CLASSES = {
    Model1Predictor.model_key: Model1Predictor,
    Model3Predictor.model_key: Model3Predictor,
}


@lru_cache
def get_predictor(model_key: str) -> PneumoniaPredictor:
    predictor_class = PREDICTOR_CLASSES.get(model_key)

    if predictor_class is None:
        raise UnsupportedModelError(
            f"지원하지 않는 예측 모델입니다: {model_key}"
        )

    return predictor_class()
