"""SPL mTLS report gateway. Never writes credentials or report tokens to logs."""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

import frappe
import requests
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

from factory_management.spl_po.parser import MAX_BYTES


class GatewayError(ValueError):
    pass


def _origin(settings):
    try:
        parsed = urlsplit((settings.base_url or "").strip())
    except ValueError:
        raise GatewayError("SPL_HOST_INVALID") from None
    hosts = frappe.conf.get("spl_po_allowed_hosts") or ["spl.fastretailing.com"]
    if isinstance(hosts, str):
        hosts = [part.strip() for part in hosts.split(",")]
    allowed = {str(host).strip().lower() for host in hosts}
    if (parsed.scheme != "https" or parsed.netloc.lower() not in allowed or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in ("", "/")):
        raise GatewayError("SPL_HOST_INVALID")
    return f"https://{parsed.netloc}/"


def _certificate_file(settings):
    if not settings.client_certificate:
        raise GatewayError("SPL_CERT_REQUIRED")
    file_doc = frappe.get_doc("File", settings.client_certificate)
    if not file_doc.is_private:
        raise GatewayError("SPL_CERT_PRIVATE_REQUIRED")
    path = Path(file_doc.get_full_path()).resolve()
    private_root = Path(frappe.get_site_path("private")).resolve()
    if not path.is_relative_to(private_root) or not path.is_file():
        raise GatewayError("SPL_CERT_INVALID")
    return path


@contextmanager
def _pem_pair(settings):
    password = settings.get_password("certificate_password") or ""
    try:
        key, certificate, chain = load_key_and_certificates(
            _certificate_file(settings).read_bytes(), password.encode("utf-8") or None
        )
    except (ValueError, TypeError):
        raise GatewayError("SPL_CERT_INVALID") from None
    if not key or not certificate:
        raise GatewayError("SPL_CERT_INVALID")
    paths = []
    try:
        for data in (
            certificate.public_bytes(Encoding.PEM) + b"".join(c.public_bytes(Encoding.PEM) for c in chain or []),
            key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()),
        ):
            fd, path = tempfile.mkstemp(prefix="spl-po-", suffix=".pem")
            paths.append(path)
            os.chmod(path, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
        yield tuple(paths)
    finally:
        for path in paths:
            Path(path).unlink(missing_ok=True)


def _request(session, method, url, timeout, **kwargs):
    try:
        response = session.request(method, url, timeout=timeout, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise GatewayError("SPL_CONNECTION_FAILED") from None
    if response.status_code != 200:
        raise GatewayError("SPL_HTTP_FAILED")
    return response


def fetch_report(settings, connection_only=False):
    origin = _origin(settings)
    user = (settings.spl_user_id or "").strip()
    password = settings.get_password("spl_password") or ""
    if not user or not password:
        raise GatewayError("SPL_CREDENTIALS_REQUIRED")
    timeout = max(10, min(int(settings.request_timeout_seconds or 120), 600))
    with _pem_pair(settings) as certificate:
        with requests.Session() as session:
            session.cert = certificate
            response = _request(session, "POST", origin + "api/mdm/auth/login", timeout,
                                json={"userId": user, "password": password})
            try:
                token = response.json()["accessToken"]
            except (ValueError, KeyError, TypeError):
                raise GatewayError("SPL_LOGIN_INVALID") from None
            if not isinstance(token, str) or not token:
                raise GatewayError("SPL_LOGIN_INVALID")
            if connection_only:
                return None, None
            cookies = {"accessToken": token}
            form = {
                "mode": settings.mode or "01",
                "answerStatusId": settings.answer_status_id or "",
                "itemBrandId": settings.item_brand_id or "",
                "yearSeasonId": settings.year_season_ids or "",
                "managementFactoryId": settings.management_factory_id or "",
                "documentStatusId": settings.document_status_ids or "",
                "offset": str(settings.report_offset or 0),
            }
            response = _request(session, "POST", origin + "api/pms/po/reportxlsxbaseoncondition",
                                timeout, files=[(key, (None, value)) for key, value in form.items()],
                                cookies=cookies)
            try:
                report_path = response.json()["filePath"]
            except (ValueError, KeyError, TypeError):
                raise GatewayError("SPL_REPORT_INVALID") from None
            if not isinstance(report_path, str):
                raise GatewayError("SPL_REPORT_INVALID")
            report_path = report_path.lstrip("/")
            if (not report_path or ".." in Path(report_path).parts or
                    any(character in report_path for character in (":", "\\", "?", "#"))):
                raise GatewayError("SPL_REPORT_INVALID")
            url = origin + "s3/" + quote(report_path, safe="/")
            response = _request(session, "GET", url, timeout, cookies=cookies, stream=True)
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise GatewayError("SPL_FILE_TOO_LARGE")
            return bytes(content), report_path
