import pytest
from datetime import datetime, timedelta
import jwt
import pyotp

from shared.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_token_jti,
    get_password_hash,
    generate_2fa_qr_code_uri,
    generate_2fa_secret,
    generate_api_key,
    verify_password,
    verify_2fa_token,
)
from shared.config import settings


@pytest.mark.unit
def test_password_hash_and_verify_roundtrip():
    password = "S3cureP@ss!"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


@pytest.mark.unit
def test_access_token_contains_standard_claims():
    token = create_access_token({"sub": "alice", "role": "system_admin"})
    payload = decode_token(token)

    assert payload["sub"] == "alice"
    assert payload["role"] == "system_admin"
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload
    assert isinstance(extract_token_jti(payload), str)


@pytest.mark.unit
def test_refresh_token_contains_standard_claims():
    token = create_refresh_token({"sub": "bob"})
    payload = decode_token(token)

    assert payload["sub"] == "bob"
    assert payload["type"] == "refresh"
    assert "iat" in payload
    assert "exp" in payload
    assert isinstance(extract_token_jti(payload), str)


@pytest.mark.unit
def test_decode_token_rejects_invalid_token():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token("not-a-valid-jwt")


@pytest.mark.unit
def test_decode_token_rejects_expired_token():
    expired = jwt.encode(
        {
            "sub": "old-user",
            "exp": datetime.utcnow() - timedelta(minutes=1),
            "iat": datetime.utcnow() - timedelta(minutes=2),
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(ValueError, match="expired"):
        decode_token(expired)


@pytest.mark.unit
def test_access_token_accepts_custom_expiry_delta():
    token = create_access_token(
        {"sub": "delta-user"}, expires_delta=timedelta(minutes=3)
    )
    payload = decode_token(token)
    assert payload["type"] == "access"


@pytest.mark.unit
def test_2fa_helpers_and_api_key():
    secret = generate_2fa_secret()
    otp = pyotp.TOTP(secret).now()
    assert verify_2fa_token(secret, otp) is True

    uri = generate_2fa_qr_code_uri(secret, "ops@example.com")
    assert "ops%40example.com" in uri or "ops@example.com" in uri

    api_key = generate_api_key()
    assert isinstance(api_key, str)
    assert len(api_key) > 20
