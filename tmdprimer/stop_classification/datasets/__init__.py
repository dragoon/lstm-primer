import abc
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Tuple, Callable, List, Dict, Any

import numpy as np
import pandas as pd
import tensorflow as tf

from tmdprimer.datagen import make_sliding_windows
from tmdprimer.stop_classification.domain.metrics import ClassificationMetric


def identity(x: Any) -> Any:
    return x


@dataclass(frozen=True)
class AnnotatedStop:
    start_time: datetime
    end_time: datetime

    @classmethod
    def from_json(cls, json_dict: Dict):
        start_time = datetime.utcfromtimestamp(json_dict["startTime"] / 1000)
        end_time = datetime.utcfromtimestamp(json_dict["endTime"] / 1000)
        return AnnotatedStop(start_time, end_time)

    @property
    def duration(self) -> timedelta:
        return self.end_time - self.start_time

    def overlap_percent(self, other: "AnnotatedStop") -> float:
        """
        Calculates maximum time different for another annotated stop on both sides
        Used to compute metrics
        """
        overlap = min(self.end_time, other.end_time) - max(self.start_time, other.start_time)
        return overlap / min(self.duration, other.duration)


class DataFile(abc.ABC):
    df: pd.DataFrame
    transport_mode: str
    label_mapping_func: Callable[[str], int] = identity
    annotated_stops: List[AnnotatedStop]

    @abc.abstractmethod
    def get_figure(self, *args, **kwargs):
        pass

    def _to_windows(self, window_size: int, overlap_size: int) -> Tuple[np.ndarray, np.ndarray]:
        df = pd.DataFrame({"linear": self.df["linear_accel"], "label": self.df["label"]}).dropna()

        # transform label values to integers
        labels = df["label"].apply(self.label_mapping_func).to_numpy()

        # fmt: off
        windows_x = make_sliding_windows(
            df[["linear", ]].to_numpy(), window_size, overlap_size=overlap_size, flatten_inside_window=False
        )
        # fmt: on
        windows_y = make_sliding_windows(labels, window_size, overlap_size=overlap_size, flatten_inside_window=False)
        return windows_x, windows_y

    def to_numpy_split_windows(self, window_size: int) -> Tuple[np.ndarray, np.ndarray]:
        return self._to_windows(window_size, 0)

    def to_numpy_sliding_windows(self, window_size: int) -> Tuple[np.ndarray, np.ndarray]:

        windows_x, windows_y = self._to_windows(window_size, window_size - 1)
        # now we need to select a single label for a window  -- middle label so we have both prev and next data
        windows_y = np.array([x[window_size // 2] for x in windows_y], dtype=int)
        return windows_x, windows_y

    def get_metrics(
        self, predicted_stops: List[AnnotatedStop], min_allowed_overlap: float = 0.8
    ) -> ClassificationMetric:
        # get stop timespans
        fp = 0
        tp = 0
        fn = 0
        true_stops = self.annotated_stops

        i = 0
        for ts in true_stops:
            if i == len(predicted_stops):
                # make sure to increment false negatives if there are no more predicted stops
                fn += 1
            while i < len(predicted_stops):
                if ts.overlap_percent(predicted_stops[i]) > min_allowed_overlap:
                    tp += 1
                    i += 1
                    break
                if predicted_stops[i].start_time > ts.start_time:
                    fn += 1
                    break
                else:
                    fp += 1
                    i += 1
        return ClassificationMetric(tp, fn, fp)

    @abc.abstractmethod
    def stop_durations(self) -> List[Dict]:
        """
        collection all durations of stops and non-stops
        :return: dict with labels as keys and durations list
        """
        pass


class Dataset(abc.ABC):
    data_files: List[DataFile]

    def to_sliding_windows_tfds(self, window_size) -> tf.data.Dataset:

        def _iter():
            for f in self.data_files:
                windows_x, windows_y = f.to_numpy_sliding_windows(window_size)
                yield from zip(windows_x, windows_y)

        return tf.data.Dataset.from_generator(
            _iter,
            output_signature=(
                tf.TensorSpec(shape=(window_size, 1), dtype=tf.float32),
                tf.TensorSpec(shape=(1,), dtype=tf.int32),
            ),
        )

    def to_split_windows_numpy(self, window_size) -> Tuple[np.ndarray, np.ndarray]:
        result_x = None
        result_y = None
        for f in self.data_files:
            windows_x, windows_y = f.to_numpy_split_windows(window_size)
            if result_x is not None:
                result_x = np.append(result_x, windows_x, axis=0)
                result_y = np.append(result_y, windows_y, axis=0)
            else:
                result_x = windows_x
                result_y = windows_y
        return result_x, result_y

    def to_sliding_windows_numpy(self, window_size) -> Tuple[np.ndarray, np.ndarray]:
        result_x = None
        result_y = None
        for f in self.data_files:
            windows_x, windows_y = f.to_numpy_sliding_windows(window_size)
            if result_x is not None:
                result_x = np.append(result_x, windows_x, axis=0)
                result_y = np.append(result_y, windows_y, axis=0)
            else:
                result_x = windows_x
                result_y = windows_y
        return result_x, result_y

    @property
    def stop_durations_df(self) -> pd.DataFrame:
        """
        collection all durations of stops and non-stops
        :return: dict with labels as keys and durations list
        """
        result = []
        for f in self.data_files:
            # ignore first / last durations just in case
            result.extend(f.stop_durations[1:-1])
        return pd.DataFrame(result)
