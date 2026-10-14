import os

import boto3
from botocore.exceptions import ClientError

# R2 berbicara S3, jadi klien boto3 biasa jalan dengan endpoint_url diarahkan ke endpoint R2 akun.
# region "auto" yang dipakai dokumen Cloudflare. Nama bucket dibaca di dalam fungsi, bukan saat import:
# di level modul hasilnya None saat .env belum dimuat
_client = None


def _bucket() -> str:
    return os.environ["R2_BUCKET_NAME"]


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )
    return _client


def put_text(key: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    _get_client().put_object(Bucket=_bucket(), Key=key, Body=text.encode("utf-8"), ContentType=content_type)


def get_text(key: str) -> str | None:
    try:
        obj = _get_client().get_object(Bucket=_bucket(), Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise
    return obj["Body"].read().decode("utf-8")


def head(key: str) -> dict | None:
    """{'size': int} kalau objeknya ada, selain itu None."""
    try:
        resp = _get_client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise
    return {"size": resp["ContentLength"]}


def presigned_url(key: str, expires_in: int = 3600) -> str:
    """Url R2 langsung berbatas waktu, supaya byte video tidak lewat Flask. Permintaan Range tetap jalan untuk scrubbing."""
    return _get_client().generate_presigned_url("get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=expires_in)


_CONTENT_TYPES = {
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def delete_prefix(prefix: str) -> int:
    """Hapus semua objek di bawah `prefix` (folder sebuah rapat), satu delete_object per key karena R2 rewel
    soal delete_objects. Mengembalikan jumlahnya."""
    client = _get_client()
    keys = []
    continuation = None
    while True:
        kwargs = {"Bucket": _bucket(), "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        keys += [obj["Key"] for obj in resp.get("Contents", [])]
        if not resp.get("IsTruncated"):
            break
        continuation = resp["NextContinuationToken"]
    for key in keys:
        client.delete_object(Bucket=_bucket(), Key=key)
    return len(keys)


def total_size_bytes() -> int:
    """Total ukuran bucket untuk dashboard admin. Menelusuri daftar per halaman (1000 key per panggilan), cukup
    untuk puluhan rapat, catat ukuran di Postgres kalau sudah ribuan objek."""
    client = _get_client()
    total = 0
    continuation = None
    while True:
        kwargs = {"Bucket": _bucket()}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        total += sum(obj["Size"] for obj in resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            break
        continuation = resp["NextContinuationToken"]
    return total


def download_to_file(key: str, local_path: str) -> None:
    """Ambil objek ke path lokal. Transkriber butuh file asli dan rekamannya dibuat di
    container lain."""
    _get_client().download_file(_bucket(), key, local_path)


def upload_recording(local_path: str, meeting_id: str, keep_local: bool = False) -> str:
    """Unggah rekaman selesai, hapus salinan lokal (kecuali keep_local), dan kembalikan key R2 (isi meetings.recording)."""
    ext = os.path.splitext(local_path)[1]
    key = f"{meeting_id}/recording{ext}"
    content_type = _CONTENT_TYPES.get(ext.lower(), "application/octet-stream")
    _get_client().upload_file(local_path, _bucket(), key, ExtraArgs={"ContentType": content_type})
    if not keep_local:
        try:
            os.remove(local_path)
        except OSError:
            pass
    return key
