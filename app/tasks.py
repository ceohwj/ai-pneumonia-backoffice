import html
import logging
import mimetypes
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import unquote, urlparse

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.celery_worker import celery_app
from app.core.config import settings
from app.models.ai_analysis_results import AIAnalysisResult
from app.models.email_jobs import EmailJob, EmailJobStatus
from app.models.medical_records import MedicalRecord
from app.models.patients import Patient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = (PROJECT_ROOT / "media").resolve()
HEATMAP_CONTENT_ID = "heatmap-image"

SYNC_DATABASE_URL = URL.create(
    "mysql+pymysql",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=int(settings.DB_PORT),
    database=settings.DB_NAME,
)
sync_engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


def _update_job(job_id: int, **values) -> None:
    with SyncSessionLocal.begin() as session:
        job = session.get(EmailJob, job_id)
        if job is None:
            return

        for field, value in values.items():
            setattr(job, field, value)


def _resolve_heatmap_path(heatmap_url: str | None) -> Path | None:
    if not heatmap_url:
        return None

    url_path = unquote(urlparse(heatmap_url).path)
    if not url_path.startswith("/media/"):
        return None

    heatmap_path = (
        MEDIA_ROOT / url_path.removeprefix("/media/")
    ).resolve()
    if MEDIA_ROOT not in heatmap_path.parents:
        raise ValueError("허용되지 않은 Heatmap 이미지 경로입니다.")

    return heatmap_path if heatmap_path.is_file() else None


def _build_email_bodies(
    patient: Patient,
    record: MedicalRecord,
    analysis: AIAnalysisResult,
    has_inline_heatmap: bool,
) -> tuple[str, str]:
    diagnosis = "폐렴 의심" if analysis.is_pneumonia else "정상"
    heatmap_text = (
        "이메일 본문에 첨부됨"
        if has_inline_heatmap
        else "등록된 이미지 없음"
    )
    plain_body = (
        f"{patient.name} 환자 AI 폐렴 예측 결과입니다.\n\n"
        f"차트 번호: {record.chart_number}\n"
        f"증상: {record.symptoms}\n"
        f"판정: {diagnosis}\n"
        f"신뢰도: {analysis.confidence}%\n"
        f"사용 모델: {analysis.ai_model}\n"
        f"예측 일시: {analysis.created_at}\n"
        f"Heatmap: {heatmap_text}\n\n"
        "이 결과는 의료진의 최종 진단을 대체하지 않습니다."
    )

    heatmap_html = (
        f'<img src="cid:{HEATMAP_CONTENT_ID}" '
        'alt="AI Grad-CAM Heatmap" '
        'style="display:block;max-width:640px;width:100%;height:auto;'
        'border-radius:8px;border:1px solid #d8dee9;">'
        if has_inline_heatmap
        else '<p style="color:#64748b;">등록된 Heatmap 이미지가 없습니다.</p>'
    )
    html_body = f"""
    <!doctype html>
    <html lang="ko">
      <body style="margin:0;padding:24px;background:#f4f7fb;font-family:Arial,sans-serif;color:#1f2937;">
        <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:12px;padding:28px;">
          <h2 style="margin-top:0;color:#24557a;">AI 폐렴 예측 결과</h2>
          <p><strong>{html.escape(patient.name)}</strong> 환자의 예측 결과입니다.</p>
          <table style="width:100%;border-collapse:collapse;margin:20px 0;">
            <tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb;">차트 번호</th><td style="padding:10px;border-bottom:1px solid #e5e7eb;">{html.escape(record.chart_number)}</td></tr>
            <tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb;">증상</th><td style="padding:10px;border-bottom:1px solid #e5e7eb;">{html.escape(record.symptoms)}</td></tr>
            <tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb;">판정</th><td style="padding:10px;border-bottom:1px solid #e5e7eb;">{diagnosis}</td></tr>
            <tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb;">신뢰도</th><td style="padding:10px;border-bottom:1px solid #e5e7eb;">{analysis.confidence}%</td></tr>
            <tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb;">사용 모델</th><td style="padding:10px;border-bottom:1px solid #e5e7eb;">{html.escape(analysis.ai_model)}</td></tr>
            <tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb;">예측 일시</th><td style="padding:10px;border-bottom:1px solid #e5e7eb;">{analysis.created_at}</td></tr>
          </table>
          <h3 style="color:#24557a;">Heatmap 이미지</h3>
          {heatmap_html}
          <p style="margin-top:24px;padding:12px;background:#fff8e6;color:#7c5c00;border-radius:8px;font-size:13px;">
            이 결과는 의료진의 최종 진단을 대체하지 않습니다.
          </p>
        </div>
      </body>
    </html>
    """
    return plain_body, html_body


def _deliver_email(
    recipient: str,
    subject: str,
    plain_body: str,
    html_body: str,
    heatmap_path: Path | None,
) -> str:
    if settings.EMAIL_DELIVERY_MODE.lower() == "console":
        logger.info(
            "Console email delivery: recipient=%s subject=%s heatmap=%s\n%s",
            recipient,
            subject,
            heatmap_path,
            plain_body,
        )
        return "개발용 콘솔 이메일 전송이 완료되었습니다."

    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST가 설정되지 않았습니다.")

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")

    if heatmap_path is not None:
        mime_type, _ = mimetypes.guess_type(heatmap_path.name)
        maintype, subtype = (
            mime_type.split("/", maxsplit=1)
            if mime_type and mime_type.startswith("image/")
            else ("image", "jpeg")
        )
        html_part = message.get_payload()[-1]
        html_part.add_related(
            heatmap_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            cid=f"<{HEATMAP_CONTENT_ID}>",
            filename=heatmap_path.name,
        )

    with smtplib.SMTP(
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        timeout=settings.SMTP_TIMEOUT_SECONDS,
    ) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)

    return f"{recipient}로 이메일 전송이 완료되었습니다."


@celery_app.task(
    bind=True,
    name="app.tasks.send_email",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=30,
    time_limit=40,
)
def send_email(self, email_job_id: int) -> dict[str, str | int]:
    now = datetime.now()
    _update_job(
        email_job_id,
        status=EmailJobStatus.STARTED,
        started_at=now,
        retry_count=self.request.retries,
        error_message=None,
    )

    try:
        with SyncSessionLocal() as session:
            job = session.get(EmailJob, email_job_id)
            if job is None:
                raise LookupError("이메일 작업을 찾을 수 없습니다.")

            record = session.get(MedicalRecord, job.record_id)
            if record is None:
                raise LookupError("진료기록을 찾을 수 없습니다.")

            patient = session.get(Patient, record.patient_id)
            if patient is None:
                raise LookupError("환자 정보를 찾을 수 없습니다.")

            analysis = session.scalar(
                select(AIAnalysisResult)
                .where(AIAnalysisResult.record_id == record.id)
                .order_by(
                    AIAnalysisResult.created_at.desc(),
                    AIAnalysisResult.id.desc(),
                )
                .limit(1)
            )
            if analysis is None:
                raise LookupError("전송할 AI 예측 결과가 없습니다.")

            heatmap_path = _resolve_heatmap_path(
                analysis.heatmap_url
            )
            plain_body, html_body = _build_email_bodies(
                patient,
                record,
                analysis,
                has_inline_heatmap=heatmap_path is not None,
            )

            result_message = _deliver_email(
                job.recipient_email,
                job.subject,
                plain_body,
                html_body,
                heatmap_path,
            )

        _update_job(
            email_job_id,
            status=EmailJobStatus.SUCCESS,
            result_message=result_message,
            completed_at=datetime.now(),
            error_message=None,
        )
        return {
            "email_job_id": email_job_id,
            "message": result_message,
        }

    except SoftTimeLimitExceeded:
        _update_job(
            email_job_id,
            status=EmailJobStatus.FAILURE,
            error_message="이메일 작업의 제한 시간을 초과했습니다.",
            completed_at=datetime.now(),
        )
        raise
    except Exception as exc:
        if self.request.retries < self.max_retries:
            _update_job(
                email_job_id,
                status=EmailJobStatus.RETRY,
                retry_count=self.request.retries + 1,
                error_message=str(exc),
            )
            raise self.retry(exc=exc)

        _update_job(
            email_job_id,
            status=EmailJobStatus.FAILURE,
            retry_count=self.request.retries,
            error_message=str(exc),
            completed_at=datetime.now(),
        )
        raise
