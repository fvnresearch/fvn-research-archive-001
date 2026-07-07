from pathlib import Path

from fvn_dfm.data_ingestion.raw_manifest import RawFileManifest, RawManifestRecord


def test_raw_manifest_append_and_validate(tmp_path: Path):
    file_path = tmp_path / "sample.json"
    file_path.write_text('{"ok": true}', encoding="utf-8")

    manifest_path = tmp_path / "raw_file_manifest.csv"
    manifest = RawFileManifest(manifest_path)
    record = RawManifestRecord.from_downloaded_file(
        path=file_path,
        source_family="test",
        source_name="unit_test",
        source_url_or_origin="local://sample",
        http_status_code=200,
        retry_count=0,
    )
    manifest.append(record)
    manifest.append(record)  # duplicate same path/checksum should be ignored

    rows = manifest.read_records()
    assert len(rows) == 1
    assert rows[0]["sha256_checksum"]
    manifest.validate()
