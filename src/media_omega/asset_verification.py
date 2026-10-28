from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .models import (
    AssetManifest,
    AssetRecord,
    CreatedAsset,
    CreativePlan,
    Decision,
    GateResult,
)


_ALLOWED_MEDIA_TOP_LEVELS = frozenset({
    "application",
    "audio",
    "image",
    "text",
    "video",
})

_PLATFORM_PRIMARY_MEDIA = {
    "youtube": frozenset({"video"}),
    "instagram": frozenset({"image", "video"}),
    "tiktok": frozenset({"video"}),
}


def _clean_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _media_type(value: object) -> str:
    clean = _clean_text(value, "media_type").casefold()
    if clean.count("/") != 1:
        raise ValueError("media_type must be a type/subtype value")
    top_level, subtype = clean.split("/", 1)
    if top_level not in _ALLOWED_MEDIA_TOP_LEVELS or not subtype.strip():
        raise ValueError("media_type is not supported")
    if any(character.isspace() for character in clean):
        raise ValueError("media_type cannot contain whitespace")
    return clean


def _read_integrity(path: Path) -> tuple[int, str]:
    before = path.stat()
    if not path.is_file():
        raise ValueError("asset path must reference a regular file")

    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)

    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or size != after.st_size
    ):
        raise RuntimeError("asset changed while integrity was being measured")
    return size, digest.hexdigest()


def capture_created_asset(asset: CreatedAsset) -> AssetRecord:
    """Capture immutable facts from one locally created asset.

    The creator declares identity, path, media type and provenance. MEDIA Ω
    independently resolves the file, measures its byte size and computes SHA256.
    """
    if not isinstance(asset, CreatedAsset):
        raise TypeError("creator assets must use CreatedAsset")

    asset_id = _clean_text(asset.asset_id, "asset_id")
    media_type = _media_type(asset.media_type)
    provenance = _clean_text(asset.provenance, "provenance")
    raw_path = _clean_text(asset.path, "path")

    try:
        resolved = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("asset file does not exist") from exc
    if not resolved.is_file():
        raise ValueError("asset path must reference a regular file")

    try:
        size, digest = _read_integrity(resolved)
    except OSError as exc:
        raise ValueError("asset file could not be read") from exc
    if size <= 0:
        raise ValueError("asset file must not be empty")

    return AssetRecord(
        asset_id=asset_id,
        path=str(resolved),
        media_type=media_type,
        sha256=digest,
        size_bytes=size,
        provenance=provenance,
    )


def verify_asset_manifest(
    manifest: AssetManifest,
    plan: CreativePlan,
) -> GateResult:
    """Verify the real files represented by one admitted manifest.

    This proves file existence, integrity, manifest ownership, declared media
    shape and generation provenance. It intentionally does not claim copyright
    certainty or independent originality proof.
    """
    reasons: list[str] = []

    def fail(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    if manifest.entity_id != plan.opportunity_id:
        fail("MANIFEST_ENTITY_MISMATCH")
    if manifest.plan_id != plan.id:
        fail("MANIFEST_PLAN_MISMATCH")
    if manifest.version != "asset_manifest.v2":
        fail("UNSUPPORTED_ASSET_MANIFEST_VERSION")
    if not isinstance(manifest.provider, str) or not manifest.provider.strip():
        fail("PROVIDER_REQUIRED")
    if not manifest.assets:
        fail("ASSETS_REQUIRED")

    asset_ids: set[str] = set()
    paths: set[str] = set()
    media_top_levels: set[str] = set()

    for index, asset in enumerate(manifest.assets):
        if not isinstance(asset, AssetRecord):
            fail(f"ASSET_RECORD_INVALID:{index}")
            continue

        if not isinstance(asset.asset_id, str) or not asset.asset_id.strip():
            fail(f"ASSET_ID_REQUIRED:{index}")
        elif asset.asset_id in asset_ids:
            fail("DUPLICATE_ASSET_ID")
        else:
            asset_ids.add(asset.asset_id)

        if not isinstance(asset.path, str) or not asset.path.strip():
            fail(f"ASSET_PATH_REQUIRED:{index}")
            continue
        if asset.path in paths:
            fail("DUPLICATE_ASSET_PATH")
        else:
            paths.add(asset.path)

        try:
            media = _media_type(asset.media_type)
            media_top_levels.add(media.split("/", 1)[0])
        except ValueError:
            fail(f"MEDIA_TYPE_INVALID:{asset.asset_id or index}")

        if not isinstance(asset.provenance, str) or not asset.provenance.strip():
            fail(f"PROVENANCE_REQUIRED:{asset.asset_id or index}")

        if (
            isinstance(asset.size_bytes, bool)
            or not isinstance(asset.size_bytes, int)
            or asset.size_bytes <= 0
        ):
            fail(f"ASSET_SIZE_INVALID:{asset.asset_id or index}")

        if (
            not isinstance(asset.sha256, str)
            or len(asset.sha256) != 64
            or any(character not in "0123456789abcdef" for character in asset.sha256)
        ):
            fail(f"ASSET_SHA256_INVALID:{asset.asset_id or index}")

        try:
            resolved = Path(asset.path).expanduser().resolve(strict=True)
            if str(resolved) != asset.path:
                fail(f"ASSET_PATH_CHANGED:{asset.asset_id or index}")
            if not resolved.is_file():
                fail(f"ASSET_NOT_FILE:{asset.asset_id or index}")
                continue
            size, digest = _read_integrity(resolved)
        except (OSError, RuntimeError, ValueError):
            fail(f"ASSET_UNREADABLE:{asset.asset_id or index}")
            continue

        if size <= 0:
            fail(f"ASSET_EMPTY:{asset.asset_id or index}")
        if size != asset.size_bytes:
            fail(f"ASSET_SIZE_MISMATCH:{asset.asset_id or index}")
        if digest != asset.sha256:
            fail(f"ASSET_HASH_MISMATCH:{asset.asset_id or index}")

    required_primary = _PLATFORM_PRIMARY_MEDIA.get(plan.platform)
    if required_primary is None:
        fail("UNSUPPORTED_PLATFORM")
    elif not (media_top_levels & required_primary):
        fail("PLATFORM_MEDIA_MISMATCH")

    if reasons:
        return GateResult(Decision.BLOCK, tuple(reasons))
    return GateResult(Decision.ACCEPT, ("ASSET_VERIFICATION_PASS",))
