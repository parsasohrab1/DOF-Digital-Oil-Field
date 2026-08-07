"""
SMS alert notifications for OGIM / SOGF.

Providers:
  - mock: stores messages in memory outbox (dev / demo)
  - kavenegar: Iranian SMS gateway (https://api.kavenegar.com)
  - twilio: international SMS
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from shared.config import settings
from shared.logging_config import setup_logging

logger = setup_logging("alert-sms")

# In-memory registry (same pattern as push devices)
SMS_RECIPIENTS: Dict[str, Dict[str, Any]] = {}
SMS_OUTBOX: List[Dict[str, Any]] = []
SMS_OUTBOX_MAX = 200


def normalize_iran_mobile(phone: str) -> str:
    """Normalize to E.164 Iran: +989xxxxxxxxx"""
    raw = (phone or "").strip()
    digits = re.sub(r"[^\d]", "", raw)
    if digits.startswith("98") and len(digits) >= 12:
        national = digits[2:]
    elif digits.startswith("0") and len(digits) >= 11:
        national = digits[1:]
    else:
        national = digits

    if not re.fullmatch(r"9\d{9}", national):
        raise ValueError(
            "شماره موبایل نامعتبر است. مثال: 09121234567 یا +989121234567"
        )
    return f"+98{national}"


def to_kavenegar_receptor(e164: str) -> str:
    """Kavenegar accepts 09xxxxxxxxx"""
    return "0" + e164[3:]


def register_sms_recipient(
    phone: str,
    *,
    label: str = "",
    enabled: bool = True,
    severities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    e164 = normalize_iran_mobile(phone)
    SMS_RECIPIENTS[e164] = {
        "phone": e164,
        "phone_display": to_kavenegar_receptor(e164),
        "label": label or "اپراتور میدان",
        "enabled": enabled,
        "severities": [s.lower() for s in (severities or ["critical", "warning"])],
        "registered_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    return SMS_RECIPIENTS[e164]


def unregister_sms_recipient(phone: str) -> bool:
    e164 = normalize_iran_mobile(phone)
    return SMS_RECIPIENTS.pop(e164, None) is not None


def list_sms_recipients() -> List[Dict[str, Any]]:
    return list(SMS_RECIPIENTS.values())


def _record_outbox(entry: Dict[str, Any]) -> None:
    SMS_OUTBOX.insert(0, entry)
    del SMS_OUTBOX[SMS_OUTBOX_MAX:]


def sms_provider_status() -> Dict[str, Any]:
    provider = (settings.SMS_PROVIDER or "mock").lower()
    ready = True
    detail = "mock outbox (پیامک واقعی ارسال نمی‌شود تا کلید API تنظیم شود)"
    if provider == "kavenegar":
        ready = bool(settings.KAVENEGAR_API_KEY)
        detail = (
            "Kavenegar آماده"
            if ready
            else "KAVENEGAR_API_KEY تنظیم نشده — به mock می‌افتد"
        )
    elif provider == "twilio":
        ready = bool(
            settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_FROM_NUMBER
        )
        detail = "Twilio آماده" if ready else "اعتبارنامه Twilio ناقص — به mock می‌افتد"
    return {
        "enabled": bool(settings.SMS_ENABLED),
        "provider": provider,
        "provider_ready": ready,
        "detail": detail,
        "severities": [
            s.strip().lower()
            for s in (settings.SMS_SEVERITIES or "critical,warning").split(",")
            if s.strip()
        ],
        "recipients": len(SMS_RECIPIENTS),
        "outbox_count": len(SMS_OUTBOX),
    }


async def _send_kavenegar(phone_e164: str, message: str) -> Dict[str, Any]:
    api_key = settings.KAVENEGAR_API_KEY
    if not api_key:
        raise RuntimeError("KAVENEGAR_API_KEY missing")
    receptor = to_kavenegar_receptor(phone_e164)
    url = f"https://api.kavenegar.com/v1/{api_key}/sms/send.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            data={
                "receptor": receptor,
                "sender": settings.KAVENEGAR_SENDER,
                "message": message,
            },
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(f"Kavenegar HTTP {resp.status_code}: {payload}")
        return {"provider": "kavenegar", "status": "sent", "response": payload}


async def _send_twilio(phone_e164: str, message: str) -> Dict[str, Any]:
    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_FROM_NUMBER
    if not (sid and token and from_number):
        raise RuntimeError("Twilio credentials incomplete")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            data={"To": phone_e164, "From": from_number, "Body": message},
            auth=(sid, token),
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(f"Twilio HTTP {resp.status_code}: {payload}")
        return {
            "provider": "twilio",
            "status": "sent",
            "sid": payload.get("sid"),
            "response": payload,
        }


async def send_sms(
    phone: str,
    message: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    e164 = normalize_iran_mobile(phone)
    provider = (settings.SMS_PROVIDER or "mock").lower()
    status_info = sms_provider_status()
    effective = provider
    result: Dict[str, Any]

    if not settings.SMS_ENABLED:
        result = {"provider": provider, "status": "disabled", "reason": "SMS_ENABLED=false"}
    elif provider == "kavenegar" and status_info["provider_ready"]:
        try:
            result = await _send_kavenegar(e164, message)
        except Exception as exc:
            logger.error("Kavenegar send failed: %s", exc)
            effective = "mock"
            result = {
                "provider": "mock",
                "status": "queued_mock",
                "fallback_from": "kavenegar",
                "error": str(exc),
            }
    elif provider == "twilio" and status_info["provider_ready"]:
        try:
            result = await _send_twilio(e164, message)
        except Exception as exc:
            logger.error("Twilio send failed: %s", exc)
            effective = "mock"
            result = {
                "provider": "mock",
                "status": "queued_mock",
                "fallback_from": "twilio",
                "error": str(exc),
            }
    else:
        effective = "mock"
        result = {
            "provider": "mock",
            "status": "queued_mock",
            "reason": status_info["detail"],
        }

    entry = {
        "id": f"sms-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        "at": datetime.utcnow().isoformat(),
        "phone": e164,
        "phone_display": to_kavenegar_receptor(e164),
        "message": message,
        "effective_provider": effective,
        "result": result,
        "meta": meta or {},
    }
    _record_outbox(entry)
    logger.info(
        "SMS %s → %s via %s (%s)",
        result.get("status"),
        e164,
        effective,
        (message[:80] + "…") if len(message) > 80 else message,
    )
    return entry


def build_alert_sms(well_name: str, severity: str, message: str, alert_id: str) -> str:
    sev = (severity or "").upper()
    return (
        f"SOGF هشدار {sev}\n"
        f"چاه: {well_name}\n"
        f"{message}\n"
        f"کد: {alert_id}\n"
        f"میدان دهلران"
    )


async def notify_alert_via_sms(
    *,
    alert_id: str,
    well_name: str,
    severity: str,
    message: str,
) -> Dict[str, Any]:
    if not settings.SMS_ENABLED:
        return {"sent": 0, "reason": "disabled"}

    allowed = {
        s.strip().lower()
        for s in (settings.SMS_SEVERITIES or "critical,warning").split(",")
        if s.strip()
    }
    sev = (severity or "").lower()
    if sev not in allowed:
        return {"sent": 0, "reason": f"severity_{sev}_not_configured"}

    recipients = [
        r
        for r in SMS_RECIPIENTS.values()
        if r.get("enabled") and sev in (r.get("severities") or allowed)
    ]
    if not recipients:
        return {"sent": 0, "reason": "no_recipients"}

    text = build_alert_sms(well_name, severity, message, alert_id)
    results = []
    for r in recipients:
        entry = await send_sms(
            r["phone"],
            text,
            meta={"alert_id": alert_id, "severity": sev, "well_name": well_name},
        )
        results.append(entry)

    return {"sent": len(results), "results": results}
