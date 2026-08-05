"""
End-of-call webhook processing. Vapi POSTs an end-of-call-report to us
after every call. The invariant here (from the Milestone 2 design): log
the raw payload to call_ingestion_logs FIRST, before any parsing, so a
call is never lost even if extraction fails -- then attempt to extract
structured fields and write a clean call_logs row, updating the
ingestion log's processing_status with the outcome either way.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import CallIngestionLog, CallLog

logger = logging.getLogger(__name__)


async def process_end_of_call(db: AsyncSession, branch_id: int, payload: dict) -> dict:
    """Returns a small dict summarising what happened, for the webhook
    response. Never raises to the caller -- a webhook that 500s just
    makes Vapi retry, and we'd rather record a 'failed' ingestion row
    and return 200 than lose the payload to retry storms."""

    # 1. Log the raw payload immediately, status 'pending'.
    message = payload.get("message", {})
    vapi_call_id = message.get("call", {}).get("id") or payload.get("call", {}).get("id")

    ingestion = CallIngestionLog(
        received_at=datetime.now(timezone.utc),
        vapi_call_id=vapi_call_id,
        branch_id=branch_id,
        raw_payload=payload,
        processing_status="pending",
    )
    db.add(ingestion)
    await db.flush()

    tables_written: dict[str, bool] = {"call_logs": False}

    try:
        # 2. Extract the fields we care about. Vapi's end-of-call-report
        # nests these under message.* -- guard every access, since a
        # call that errored early may be missing most of them.
        analysis = message.get("analysis", {}) or {}
        artifact = message.get("artifact", {}) or {}

        transcript = message.get("transcript") or artifact.get("transcript")
        summary = analysis.get("summary")
        duration_seconds = message.get("durationSeconds")
        if duration_seconds is not None:
            duration_seconds = int(duration_seconds)
        recording_url = message.get("recordingUrl") or artifact.get("recordingUrl")
        ended_reason = message.get("endedReason")
        cost = message.get("cost")

        # success evaluation is sometimes a bool, sometimes a string
        success_eval = analysis.get("successEvaluation")
        outcome = None
        if success_eval is not None:
            outcome = "success" if str(success_eval).lower() in ("true", "pass", "success") else "unresolved"
        elif ended_reason:
            outcome = str(ended_reason)

        # 3. Write the clean call_logs row.
        call_log = CallLog(
            branch_id=branch_id,
            transcript=transcript,
            summary=summary,
            duration_seconds=duration_seconds,
            recording_url=recording_url,
            outcome=outcome,
            cost=cost,
        )
        db.add(call_log)
        await db.flush()
        tables_written["call_logs"] = True

        ingestion.processing_status = "success"
        ingestion.processing_message = "Call log written."
        ingestion.tables_written = tables_written
        ingestion.customer_phone = (
            message.get("customer", {}).get("number") if isinstance(message.get("customer"), dict) else None
        )
        ingestion.extracted_data = {
            "ended_reason": ended_reason,
            "outcome": outcome,
            "has_transcript": transcript is not None,
            "has_recording": recording_url is not None,
        }
        await db.commit()
        return {"status": "processed", "call_log_written": True}

    except Exception as exc:
        # Don't lose the payload -- mark the ingestion row failed and
        # commit THAT, so we keep the raw data for later reprocessing.
        logger.exception("end_of_call: extraction/write failed")
        ingestion.processing_status = "failed"
        ingestion.processing_message = f"{type(exc).__name__}: {exc}"[:500]
        ingestion.tables_written = tables_written
        await db.commit()
        return {"status": "logged_but_processing_failed", "call_log_written": False}
