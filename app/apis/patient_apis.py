import logging
import shutil
from pathlib import Path as FilePath
from typing import Annotated
from urllib.parse import unquote, urlparse
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import require_permissions
from app.core.db.databases import async_get_db
from app.core.timeout import TimeoutRoute
from app.models.medical_records import MedicalRecord
from app.models.patients import GenderEnum, Patient
from app.models.users import (
    DepartmentEnum,
    RoleEnum,
    User,
)
from app.schemas.patient import (
    PatientCreate,
    PatientDetailResponse,
    PatientGender,
    PatientResponse,
    PatientUpdateRequest,
)
#####################################################
# 1. 라우터 선언
#####################################################
router = APIRouter(
    prefix="/patient_api", 
    tags=["patient"],
    route_class=TimeoutRoute,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = FilePath(__file__).resolve().parents[2]
MEDIA_DIR = (PROJECT_ROOT / "media").resolve()
QUARANTINE_ROOT = (
    PROJECT_ROOT / ".delete-quarantine"
).resolve()


def _to_patient_response(
    patient: Patient,
) -> PatientResponse:
    """Patient ORM 객체를 공개 API 응답 형식으로 변환합니다."""

    gender_mapping = {
        GenderEnum.M: PatientGender.MALE,
        GenderEnum.F: PatientGender.FEMALE,
    }

    return PatientResponse(
        id=patient.id,
        name=patient.name,
        age=patient.age,
        gender=gender_mapping.get(patient.gender),
        phone_number=patient.phone,
        email=patient.email,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


def _resolve_media_path(file_url: str) -> FilePath:
    """공개 /media URL을 로컬 경로로 변환하고 경로 이탈을 차단합니다."""

    url_path = unquote(urlparse(file_url).path)

    if not url_path.startswith("/media/"):
        raise ValueError(
            "허용되지 않은 미디어 파일 경로입니다."
        )

    relative_path = url_path.removeprefix("/media/")
    file_path = (MEDIA_DIR / relative_path).resolve()

    # ../ 등을 이용해 media 디렉터리 밖의 파일을 삭제하는 것을 방지합니다.
    if MEDIA_DIR not in file_path.parents:
        raise ValueError(
            "허용되지 않은 미디어 파일 경로입니다."
        )

    return file_path


def _restore_quarantined_files(
    moved_files: list[tuple[FilePath, FilePath]],
) -> None:
    """DB 삭제 실패 시 격리한 파일을 원래 위치로 복구합니다."""

    for original_path, quarantined_path in reversed(
        moved_files
    ):
        if not quarantined_path.exists():
            continue

        original_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.move(
            str(quarantined_path),
            str(original_path),
        )


def _quarantine_media_files(
    file_urls: list[str],
) -> tuple[
    FilePath,
    list[tuple[FilePath, FilePath]],
]:
    """
    DB 커밋 전에 파일을 공개 media 폴더 밖으로 이동합니다.

    DB 삭제가 실패하면 원위치로 복구하고,
    성공하면 격리 파일을 영구 삭제합니다.
    """

    quarantine_dir = (
        QUARANTINE_ROOT / uuid4().hex
    )
    moved_files: list[
        tuple[FilePath, FilePath]
    ] = []

    try:
        # 같은 파일 URL이 여러 번 저장돼 있어도 한 번만 이동합니다.
        for file_url in set(file_urls):
            original_path = _resolve_media_path(
                file_url
            )

            if not original_path.exists():
                # 파일 누락 때문에 DB 삭제 전체를 중단하지는 않습니다.
                logger.warning(
                    "삭제 대상 파일이 존재하지 않습니다: %s",
                    original_path,
                )
                continue

            if not original_path.is_file():
                # 디렉터리 등의 경로는 안전을 위해 삭제를 중단합니다.
                raise OSError(
                    "삭제 대상이 파일이 아닙니다: "
                    f"{original_path}"
                )

            relative_path = (
                original_path.relative_to(MEDIA_DIR)
            )
            quarantined_path = (
                quarantine_dir / relative_path
            )

            quarantined_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            # Docker named volume과 bind mount는 서로 다른 파일시스템일 수
            # 있으므로 os.replace 기반 Path.replace 대신 shutil.move를 사용합니다.
            shutil.move(
                str(original_path),
                str(quarantined_path),
            )
            moved_files.append(
                (original_path, quarantined_path)
            )

    except Exception:
        _restore_quarantined_files(moved_files)
        shutil.rmtree(
            quarantine_dir,
            ignore_errors=True,
        )
        raise

    return quarantine_dir, moved_files

#####################################################
# 2. API Endpoints 구현
#####################################################

# 환자 등록 API
@router.post(
    "/v1/patients/",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="환자 정보 등록 API",
    description="의료 실무진이 환자 정보를 등록합니다.",
)
async def create_patient(
    body: PatientCreate,
    current_user=Depends(
        require_permissions(
            allowed_departments=(
                DepartmentEnum.MEDICAL,
            ),
            allowed_roles=(
                RoleEnum.STAFF,
            ),
        )
    ),
    db: AsyncSession = Depends(async_get_db),
) -> PatientResponse:
    patient = Patient(
        name=body.name,
        age=body.age,
        gender=(
            GenderEnum.M
            if body.gender == PatientGender.MALE
            else GenderEnum.F
        ),
        phone=body.phone_number,
        email=str(body.email) if body.email else None,
    )

    db.add(patient)

    try:
        await db.commit()
        await db.refresh(patient)
    except SQLAlchemyError as error:
        await db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "환자 정보 등록 중 오류가 발생했습니다."
            ),
        ) from error

    return PatientResponse(
        id=patient.id,
        name=patient.name,
        age=patient.age,
        gender=(
            PatientGender.MALE
            if patient.gender == GenderEnum.M
            else PatientGender.FEMALE
        ),
        phone_number=patient.phone,
        email=patient.email,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


# 환자 목록 조회 API
@router.get(
    "/v1/patients/",
    response_model=list[PatientResponse],
    status_code=status.HTTP_200_OK,
    summary="환자 목록 조회 API",
    description=(
        "환자 이름 검색과 성별 및 나이 범위 "
        "필터링을 지원합니다."
    ),
)
async def get_patient_list(
    name: str | None = Query(
        default=None,
        min_length=1,
        max_length=30,
        description="환자 이름 검색어",
    ),
    gender: PatientGender | None = Query(
        default=None,
        description="성별 필터: male 또는 female",
    ),
    min_age: int | None = Query(
        default=None,
        ge=0,
        le=150,
        description="최소 나이",
    ),
    max_age: int | None = Query(
        default=None,
        ge=0,
        le=150,
        description="최대 나이",
    ),
    current_user=Depends(
        require_permissions(
            allowed_roles=(
                RoleEnum.STAFF,
            ),
        )
    ),
    db: AsyncSession = Depends(async_get_db),
) -> list[PatientResponse]:
    if (
        min_age is not None
        and max_age is not None
        and min_age > max_age
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=[
                {
                    "loc": ["query", "min_age"],
                    "msg": (
                        "min_age는 max_age보다 "
                        "클 수 없습니다."
                    ),
                    "type": "value_error",
                }
            ],
        )

    statement = select(Patient)

    if name:
        search_name = name.strip()
        statement = statement.where(
            Patient.name.contains(search_name)
        )

    if gender:
        db_gender = (
            GenderEnum.M
            if gender == PatientGender.MALE
            else GenderEnum.F
        )
        statement = statement.where(
            Patient.gender == db_gender
        )

    if min_age is not None:
        statement = statement.where(
            Patient.age >= min_age
        )

    if max_age is not None:
        statement = statement.where(
            Patient.age <= max_age
        )

    statement = statement.order_by(
        Patient.id.desc()
    )

    try:
        result = await db.execute(statement)
        patients = result.scalars().all()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "환자 목록 조회 중 오류가 발생했습니다."
            ),
        ) from error

    return [
        PatientResponse(
            id=patient.id,
            name=patient.name,
            age=patient.age,
            gender=(
                PatientGender.MALE
                if patient.gender == GenderEnum.M
                else PatientGender.FEMALE
            ),
            phone_number=patient.phone,
            email=patient.email,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
        )
        for patient in patients
    ]


# 환자 상세 정보 조회 API
@router.get(
    "/v1/patients/{patient_id}",
    response_model=PatientDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="환자 정보 상세 조회 API",
    description=(
        "환자 고유 ID를 기준으로 환자의 "
        "상세 정보를 조회합니다."
    ),
)
async def get_patient_detail(
    patient_id: int = Path(
        ...,
        ge=1,
        description="환자 고유 ID",
    ),
    current_user=Depends(
        require_permissions(
            allowed_roles=(
                RoleEnum.STAFF,
            ),
        )
    ),
    db: AsyncSession = Depends(async_get_db),
) -> PatientDetailResponse:
    statement = select(Patient).where(
        Patient.id == patient_id
    )

    try:
        result = await db.execute(statement)
        patient = result.scalar_one_or_none()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "환자 정보 상세 조회 중 "
                "오류가 발생했습니다."
            ),
        ) from error

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 환자를 찾을 수 없습니다.",
        )

    return PatientDetailResponse(
        name=patient.name,
        gender=(
            PatientGender.MALE
            if patient.gender == GenderEnum.M
            else PatientGender.FEMALE
        ),
        phone_number=patient.phone,
        email=patient.email,
        age=patient.age,
    )

# 환자 정보 수정 API
@router.patch(
    "/v1/patients/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
    summary="환자 정보 수정 API",
)
async def update_patient(
    patient_id: Annotated[int, Path(ge=1)],
    body: PatientUpdateRequest,
    db: AsyncSession = Depends(async_get_db),
    _current_user: User = Depends(
        require_permissions(
            allowed_roles=(RoleEnum.STAFF,),
        )
    ),
) -> PatientResponse:
    try:
        statement = select(Patient).where(
            Patient.id == patient_id
        )

        result = await db.execute(statement)
        patient = result.scalar_one_or_none()

        if patient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 환자를 찾을 수 없습니다.",
            )

        patient.name = body.name
        patient.phone = body.phone_number
        patient.email = str(body.email) if body.email else None

        await db.commit()
        await db.refresh(patient)

    except HTTPException:
        raise

    except SQLAlchemyError as error:
        await db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "환자 정보 수정 중 오류가 발생했습니다."
            ),
        ) from error

    return _to_patient_response(patient)

#환자 정보 삭제 API
@router.delete(
    "/v1/patients/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="환자 정보 삭제 API",
)
async def delete_patient(
    patient_id: Annotated[int, Path(ge=1)],
    db: AsyncSession = Depends(async_get_db),
    _current_user: User = Depends(
        require_permissions(
            allowed_roles=(RoleEnum.STAFF,),
        )
    ),
) -> Response:
    quarantine_dir: FilePath | None = None
    moved_files: list[
        tuple[FilePath, FilePath]
    ] = []

    try:
        statement = (
            select(Patient)
            .options(
                # ORM cascade와 파일 경로 수집을 위해 관계를 미리 로드합니다.
                selectinload(
                    Patient.medical_records
                ).selectinload(
                    MedicalRecord.xray_images
                ),
                selectinload(
                    Patient.medical_records
                ).selectinload(
                    MedicalRecord.ai_analysis_results
                ),
            )
            .where(Patient.id == patient_id)
        )

        result = await db.execute(statement)
        patient = result.scalar_one_or_none()

        if patient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 환자를 찾을 수 없습니다.",
            )

        # ORM 삭제 전에 X-ray와 Heatmap 파일 경로를 수집합니다.
        file_urls: list[str] = []

        for medical_record in patient.medical_records:
            file_urls.extend(
                xray.image_url
                for xray in medical_record.xray_images
            )
            file_urls.extend(
                analysis.heatmap_url
                for analysis
                in medical_record.ai_analysis_results
                if analysis.heatmap_url
            )

        # 1. DB 삭제 전에 파일을 공개 media 경로 밖으로 격리합니다.
        quarantine_dir, moved_files = (
            _quarantine_media_files(file_urls)
        )

        # 2. ORM cascade로 환자와 모든 연관 데이터를 삭제합니다.
        await db.delete(patient)
        await db.commit()

    except HTTPException:
        raise

    except (
        SQLAlchemyError,
        OSError,
        ValueError,
    ) as error:
        await db.rollback()

        logger.exception(
            "환자 정보 삭제 실패: patient_id=%s",
            patient_id,
        )

        # DB 삭제가 실패했으므로 격리 파일을 원래 위치로 복구합니다.
        try:
            _restore_quarantined_files(
                moved_files
            )
        except OSError:
            logger.exception(
                "격리 파일 복구 중 오류가 발생했습니다."
            )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "환자 정보 삭제 중 오류가 발생했습니다."
            ),
        ) from error

    # 3. DB 삭제가 확정된 후 격리 파일을 영구 삭제합니다.
    if (
        quarantine_dir is not None
        and quarantine_dir.exists()
    ):
        try:
            shutil.rmtree(
                quarantine_dir,
                ignore_errors=False,
            )
        except OSError:
            # DB commit 이후에는 롤백할 수 없습니다.
            # 파일은 공개 media 밖에 있으므로 후속 정리 대상으로 둡니다.
            logger.exception(
                "격리 파일 영구 삭제 중 오류가 발생했습니다: %s",
                quarantine_dir,
            )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )
