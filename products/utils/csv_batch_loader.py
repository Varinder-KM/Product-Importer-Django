import csv
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple


Row = Dict[str, str]
RowWithLineNumber = Tuple[int, Row]


class CSVBatchLoader:
    """Utility to iterate over CSV rows in fixed-size batches."""

    def __init__(self, file_path: Path, batch_size: int = 5000, encoding: str = "utf-8") -> None:
        self.file_path = Path(file_path)
        self.batch_size = batch_size
        self.encoding = encoding

    def count_rows(self) -> int:
        """Count data rows (excluding header)."""
        total = 0
        with self.file_path.open(newline="", encoding=self.encoding) as csvfile:
            reader = csv.reader(csvfile)
            for index, _ in enumerate(reader):
                if index == 0:
                    continue  # skip header
                total += 1
        return total

    def iter_batches(self) -> Iterator[List[RowWithLineNumber]]:
        """Yield batches of rows with their original line numbers."""
        with self.file_path.open(newline="", encoding=self.encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file must include a header row.")

            batch: List[RowWithLineNumber] = []
            line_number = 1  # header line

            for row in reader:
                line_number += 1
                batch.append((line_number, row))
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []

            if batch:
                yield batch

    def __iter__(self) -> Iterable[List[RowWithLineNumber]]:
        return self.iter_batches()

