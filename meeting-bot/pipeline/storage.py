import os

import boto3
from botocore.exceptions import ClientError

# R2 is S3-compatible — boto3's plain S3 client works against it by just
# pointing endpoint_url at Cloudflare's per-account R2 endpoint instead of
# AWS. region_name is required by boto3 but meaningless to R2 itself,
# "auto" is what Cloudflare's own docs use.
#
# Deliberately not read at module level (`_BUCKET = os.getenv(...)` up
# here) — that already bit this module once: app.py used to import this
# before calling load_dotenv(), so os.environ didn't have R2_BUCKET_NAME
# yet and this silently became None, forever, for the life of the process.
# Reading it lazily inside a function call is immune to that regardless of
# what order a caller happens to import things in.
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
    """{'size': int} if the object exists, else None — used for the
    recording's displayed file size."""
    try:
        resp = _get_client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise
    return {"size": resp["ContentLength"]}


def presigned_url(key: str, expires_in: int = 3600) -> str:
    """A time-limited direct-to-R2 URL — used instead of proxying video
    bytes through Flask (send_file) or making the bucket public. Standard
    HTTP Range requests still work against it, so <video> scrubbing/seeking
    isn't lost by not serving the file ourselves."""
    return _get_client().generate_presigned_url("get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=expires_in)


_CONTENT_TYPES = {
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def total_size_bytes() -> int:
    """Sums every object's size in the bucket — used for the super admin
    dashboard's storage metric. Paginates since list_objects_v2 caps at
    1000 keys per call; fine at this app's scale (tens of meetings), would
    need a cheaper approach (e.g. tracking sizes in Postgres on upload) if
    the bucket ever grew into the tens of thousands of objects."""
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


def upload_recording(local_path: str, meeting_id: str) -> str:
    """Uploads a finished recording to R2 and deletes the local copy — the
    actual "off local disk" part of this migration. Everything upstream
    (bots/base.py's chunk relay while a recording is still live) still needs
    a local file to write to as chunks arrive; this is just the handoff
    once that's done. Returns the R2 key, which becomes what the meetings
    table's `recording` column holds from here on."""
    ext = os.path.splitext(local_path)[1]
    key = f"{meeting_id}/recording{ext}"
    content_type = _CONTENT_TYPES.get(ext.lower(), "application/octet-stream")
    _get_client().upload_file(local_path, _bucket(), key, ExtraArgs={"ContentType": content_type})
    try:
        os.remove(local_path)
    except OSError:
        pass
    return key
