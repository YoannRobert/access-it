import pandas as pd


ROW_HEIGHT = 35  # pixels per row, header included


def table_height(df: pd.DataFrame, max_rows: int = 20) -> int:
    """Height showing every row of the table, up to max_rows rows, then scrolling."""
    return ROW_HEIGHT * (min(len(df), max_rows) + 1) + 3
