"""Snapshot of the database: one Parquet file per table in a ZIP archive (writing and reading)."""

import io
import pandas as pd
import zipfile

from pathlib import Path


def build_snapshot_zip(tables: dict[str, pd.DataFrame], zip_path: Path) -> Path:
    """Write each DataFrame as a Parquet file inside a single ZIP archive."""
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for table_name, df in tables.items():
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            zf.writestr(f"{table_name}.parquet", buffer.getvalue())
    return zip_path


def read_snapshot_zip(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Read a snapshot archive (see build_snapshot_zip) into DataFrames, by table name.

    Raises:
        ValueError: If the archive holds a file other than a Parquet file.
    """
    tables = {}
    with zipfile.ZipFile(zip_path, mode="r") as zf:
        for name in zf.namelist():
            table_name, suffix = Path(name).stem, Path(name).suffix
            if suffix != ".parquet" or Path(name).name != name:
                raise ValueError(f"Unexpected file in the snapshot {zip_path.name}: {name}")
            tables[table_name] = pd.read_parquet(io.BytesIO(zf.read(name)))
    return tables
