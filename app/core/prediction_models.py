AI_MODEL_BY_KEY = {
    "model_1": "strict_focal_clahe_letterbox_384_5fold",
    "model_3": "jihye_resnet18_simplecnn_densenet121_v1",
}


def get_ai_model_name(model_key: str) -> str:
    try:
        return AI_MODEL_BY_KEY[model_key]
    except KeyError as exc:
        raise ValueError(
            f"지원하지 않는 예측 모델입니다: {model_key}"
        ) from exc
