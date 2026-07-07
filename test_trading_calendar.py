from pathlib import Path
import zipfile

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import (
    fsds_zip_url,
    ingest_fsds_zip,
    parse_fsds_zip_label,
    parse_quarters,
    parse_years,
    quarter_label,
    validate_fsds_zip,
)


def make_sample_fsds_zip(path: Path) -> None:
    sub = (
        "adsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\taccepted\tinstance\n"
        "0000320193-23-000106\t320193\tAPPLE INC\t10-K\t20230930\t2023\tFY\t20231103\t2023-11-03 18:10:43\taapl-20230930_htm.xml\n"
        "0000320193-23-000001\t320193\tAPPLE INC\t8-K\t20230101\t2023\tQ1\t20230101\t2023-01-01 00:00:00\taapl-8k.xml\n"
    )
    num = (
        "adsh\ttag\tversion\tcoreg\tddate\tqtrs\tuom\tvalue\tfootnote\n"
        "0000320193-23-000106\tRevenues\tus-gaap/2023\t\t20230930\t4\tUSD\t383285000000\t\n"
        "0000320193-23-000106\tNetIncomeLoss\tus-gaap/2023\t\t20230930\t4\tUSD\t96995000000\t\n"
        "0000320193-23-000001\tRevenues\tus-gaap/2023\t\t20230101\t0\tUSD\t1\t\n"
    )
    tag = (
        "tag\tversion\tcustom\tabstract\tdatatype\tiord\tcrdr\ttlabel\tdoc\n"
        "Revenues\tus-gaap/2023\t0\t0\tmonetary\tI\tC\tRevenues\tRevenue description\n"
        "NetIncomeLoss\tus-gaap/2023\t0\t0\tmonetary\tI\tC\tNet Income\tNet income description\n"
    )
    pre = (
        "adsh\treport\tline\tstmt\tinpth\trfile\ttag\tversion\tplabel\tnegating\n"
        "0000320193-23-000106\t1\t1\tIS\t0\tH\tRevenues\tus-gaap/2023\tRevenues\t0\n"
        "0000320193-23-000106\t1\t2\tIS\t0\tH\tNetIncomeLoss\tus-gaap/2023\tNet Income\t0\n"
        "0000320193-23-000001\t1\t1\tIS\t0\tH\tRevenues\tus-gaap/2023\tRevenues\t0\n"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("sub.txt", sub)
        zf.writestr("num.txt", num)
        zf.writestr("tag.txt", tag)
        zf.writestr("pre.txt", pre)


def test_quarter_label_and_url():
    assert quarter_label(2024, 1) == "2024q1"
    assert fsds_zip_url(2024, 1).endswith("/2024q1.zip")


def test_parse_fsds_zip_label():
    assert parse_fsds_zip_label("2024q3.zip") == (2024, 3)


def test_parse_years_and_quarters():
    assert parse_years("2020-2022") == (2020, 2021, 2022)
    assert parse_years("2020,2022") == (2020, 2022)
    assert parse_quarters("1,3") == (1, 3)


def test_validate_and_ingest_fsds_zip(tmp_path: Path):
    zip_path = tmp_path / "2023q4.zip"
    make_sample_fsds_zip(zip_path)
    validate_fsds_zip(zip_path)

    tables = ingest_fsds_zip(zip_path, forms_filter=("10-K", "10-Q"), chunksize=1)
    assert set(tables.keys()) == {"sub", "num", "tag", "pre"}
    assert len(tables["sub"]) == 1
    assert len(tables["num"]) == 2
    assert len(tables["pre"]) == 2
    assert tables["sub"].iloc[0]["form"] == "10-K"
    assert tables["num"]["adsh"].nunique() == 1
    assert "fsds_quarter_label" in tables["num"].columns
