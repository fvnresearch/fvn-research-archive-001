from pathlib import Path
import zipfile

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import (
    FSDSIngestionConfig,
    build_fsds_source_tables,
)


def make_sample_fsds_zip(path: Path, accession: str) -> None:
    sub = (
        "adsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\taccepted\tinstance\n"
        f"{accession}\t320193\tAPPLE INC\t10-K\t20230930\t2023\tFY\t20231103\t2023-11-03 18:10:43\taapl.xml\n"
    )
    num = (
        "adsh\ttag\tversion\tcoreg\tddate\tqtrs\tuom\tvalue\tfootnote\n"
        f"{accession}\tRevenues\tus-gaap/2023\t\t20230930\t4\tUSD\t383285000000\t\n"
        f"{accession}\tNetIncomeLoss\tus-gaap/2023\t\t20230930\t4\tUSD\t96995000000\t\n"
    )
    tag = (
        "tag\tversion\tcustom\tabstract\tdatatype\tiord\tcrdr\ttlabel\tdoc\n"
        "Revenues\tus-gaap/2023\t0\t0\tmonetary\tI\tC\tRevenues\tRevenue description\n"
        "NetIncomeLoss\tus-gaap/2023\t0\t0\tmonetary\tI\tC\tNet Income\tNet income description\n"
    )
    pre = (
        "adsh\treport\tline\tstmt\tinpth\trfile\ttag\tversion\tplabel\tnegating\n"
        f"{accession}\t1\t1\tIS\t0\tH\tRevenues\tus-gaap/2023\tRevenues\t0\n"
        f"{accession}\t1\t2\tIS\t0\tH\tNetIncomeLoss\tus-gaap/2023\tNet Income\t0\n"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("sub.txt", sub)
        zf.writestr("num.txt", num)
        zf.writestr("tag.txt", tag)
        zf.writestr("pre.txt", pre)


def test_build_fsds_source_tables(tmp_path: Path):
    raw_dir = tmp_path / "raw_fsds"
    raw_dir.mkdir()
    make_sample_fsds_zip(raw_dir / "2023q4.zip", "0000320193-23-000106")

    config = FSDSIngestionConfig(
        raw_fsds_dir=raw_dir,
        output_dir=tmp_path / "source_tables",
        diagnostics_dir=tmp_path / "diagnostics",
        years=(2023,),
        quarters=(4,),
        forms_filter=("10-K", "10-Q"),
        chunksize=1,
    )
    outputs = build_fsds_source_tables(config)

    assert len(outputs["sub"]) == 1
    assert len(outputs["num"]) == 2
    assert (tmp_path / "source_tables" / "xbrl_submission_metadata.csv").exists()
    assert (tmp_path / "source_tables" / "xbrl_fact_accession_raw.csv").exists()
    assert (tmp_path / "source_tables" / "xbrl_tag_metadata.csv").exists()
    assert (tmp_path / "source_tables" / "xbrl_presentation_metadata.csv").exists()
    assert (tmp_path / "diagnostics" / "sec_fsds_ingestion_diagnostics.csv").exists()
