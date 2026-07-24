# 이메일 백그라운드 작업

## DB 설계

`patients.email`은 기존 환자 데이터와의 호환성을 위해 nullable로 추가합니다. `email_jobs`는 API 요청과 Celery 실행 결과를 영속적으로 추적하는 감사 로그입니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `id` | BIGINT PK | 작업 고유 ID |
| `task_id` | VARCHAR(50) UNIQUE | Celery 작업 ID |
| `record_id` | BIGINT FK | 진료기록 ID, 삭제 시 작업도 삭제 |
| `requested_by` | INT FK NULL | 요청자 ID, 사용자 삭제 시 NULL |
| `recipient_email` | VARCHAR(255) | 요청 당시 수신 주소 스냅샷 |
| `subject` | VARCHAR(255) | 이메일 제목 |
| `status` | ENUM | PENDING, STARTED, SUCCESS, RETRY, FAILURE |
| `retry_count` | SMALLINT | 현재 재시도 횟수 |
| `result_message` | TEXT NULL | 성공 결과 |
| `error_message` | TEXT NULL | 최근 오류 |
| `created_at` 등 | DATETIME | 생성, 시작, 완료, 수정 시각 |

## 실행 흐름

1. 화면이 `POST /email_api/v1/medical-records/{record_id}/email-jobs`를 호출합니다.
2. FastAPI가 권한, 환자 이메일, AI 결과를 검증하고 `email_jobs`를 PENDING으로 저장합니다.
3. Celery가 Redis의 `email_queue`에서 작업을 가져가 이메일을 전송합니다.
4. 화면은 `GET /email_api/v1/email-jobs/{id}`를 호출해 상태를 확인합니다.
5. 실패 시 60초 간격으로 최대 3회 재시도하며, 작업은 30초 soft limit와 40초 hard limit를 가집니다.

개발 기본값인 `EMAIL_DELIVERY_MODE=console`은 worker 로그에 이메일을 출력합니다. 실제 SMTP 전송은 `.env`에 다음 값을 설정합니다.

```dotenv
EMAIL_DELIVERY_MODE=smtp
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=example
SMTP_PASSWORD=secret
SMTP_FROM_EMAIL=noreply@example.com
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=10
```
