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
