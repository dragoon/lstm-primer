import os
import json
from datetime import timedelta, datetime
from unittest import TestCase, main

from tmdprimer.stop_classification.datasets.dvdt_dataset import DVDTFile, DVDTDataset, AnnotatedStop


class TestDVDTFile(TestCase):
    test_file: DVDTFile

    def setUp(self):
        super().setUp()
        file_path = os.path.dirname(os.path.realpath(__file__))
        self.test_file = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data.json")))

    def test_to_numpy_sliding_windows(self):
        window_size = 4
        x, y = self.test_file.to_numpy_sliding_windows(window_size=window_size)
        true_windows_len = len(self.test_file.df) - (window_size - 1)
        self.assertEquals(len(x), true_windows_len)
        # each element in X has shape of (window_size, 1)
        self.assertEquals(x[0].shape, (window_size, 1))
        # labels is (1,)
        self.assertEquals(y[0].shape, (1,))

    def test_to_numpy_split_windows(self):
        window_size = 4
        x, y = self.test_file.to_numpy_split_windows(window_size=window_size)
        true_windows_len = len(self.test_file.df) // window_size
        self.assertEquals(len(x), true_windows_len)
        # each element in X has shape of (window_size, 1)
        self.assertEquals(x[0].shape, (window_size, 1))
        # labels here is the same
        self.assertEquals(y[0].shape, (window_size, 1))


class TestDVDTLoader(TestCase):
    test_file: DVDTFile

    def setUp(self):
        super().setUp()
        file_path = os.path.dirname(os.path.realpath(__file__))
        self.test_file = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data.json")))
        self.dataset = DVDTDataset([self.test_file])

    def test_to_window_tfds(self):
        window_size = 5
        tfds = list(self.dataset.to_sliding_windows_tfds(window_size=window_size).as_numpy_iterator())
        true_windows_size = sum(len(s.df) for s in self.dataset.data_files) - len(self.dataset.data_files) * (
            window_size - 1
        )
        self.assertEquals(len(tfds), true_windows_size)
        # each element has 2 element tuple -- features and labels
        self.assertEquals(len(tfds[0]), 2)
        # features has shape of (window_size, 1)
        self.assertEquals(tfds[0][0].shape, (window_size, 1))
        # labels is (1,)
        self.assertEquals(tfds[0][1].shape, (1,))

    def test_to_overlapping_window_numpy(self):
        window_size = 5
        # need > 1 file to test
        file_path = os.path.dirname(os.path.realpath(__file__))
        test_file1 = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data.json")))
        test_file2 = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data.json")))
        dataset = DVDTDataset([test_file1, test_file2])
        x, y = dataset.to_sliding_windows_numpy(window_size=5)
        true_windows_len = sum(len(s.df) for s in dataset.data_files) - len(dataset.data_files) * (window_size - 1)
        self.assertEquals(len(x), true_windows_len)
        # each element in X has shape of (window_size, 1)
        self.assertEquals(x[0].shape, (window_size, 1))
        # labels is (1,)
        self.assertEquals(y[0].shape, (1,))

    def test_to_split_window_numpy(self):
        window_size = 5
        # need > 1 file to test
        file_path = os.path.dirname(os.path.realpath(__file__))
        test_file1 = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data.json")))
        test_file2 = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data.json")))
        dataset = DVDTDataset([test_file1, test_file2])
        x, y = dataset.to_split_windows_numpy(window_size=5)
        true_windows_len = sum(len(s.df)//window_size for s in dataset.data_files)
        self.assertEquals(len(x), true_windows_len)
        # each element in X has shape of (window_size, 1)
        self.assertEquals(x[0].shape, (window_size, 1))
        # labels is (1,)
        self.assertEquals(y[0].shape, (window_size, 1))

    def test_stop_durations(self):
        durations = self.dataset.stop_durations_df["duration"].to_list()
        self.assertEqual(durations, [timedelta(milliseconds=2)])


class TestEmptyDVDTLoader(TestCase):
    """Check everything works with an empty file"""
    test_file: DVDTFile

    def test_empty_file(self):
        file_path = os.path.dirname(os.path.realpath(__file__))
        self.test_file = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data_empty.json")))
        self.dataset = DVDTDataset([self.test_file])


class TestMetrics(TestCase):
    test_file: DVDTFile

    def setUp(self):
        super().setUp()
        file_path = os.path.dirname(os.path.realpath(__file__))
        self.test_file = DVDTFile.from_json(json.load(open(f"{file_path}/accel_data_many_stops.json")))
        self.dataset = DVDTDataset([self.test_file])

    def test_precision_recall_correct(self):
        predicted_stops = [
            AnnotatedStop(datetime.utcfromtimestamp(10), datetime.utcfromtimestamp(15)),
            AnnotatedStop(datetime.utcfromtimestamp(25), datetime.utcfromtimestamp(30)),
        ]

        metric = self.test_file.get_metrics(predicted_stops)
        self.assertEqual(metric.tp, 2)
        self.assertEqual(metric.fp, 0)
        self.assertEqual(metric.fn, 0)

    def test_precision_correct(self):
        predicted_stops = [AnnotatedStop(datetime.utcfromtimestamp(10), datetime.utcfromtimestamp(15))]

        metric = self.test_file.get_metrics(predicted_stops)
        self.assertEqual(metric.tp, 1)
        self.assertEqual(metric.fp, 0)
        self.assertEqual(metric.fn, 1)

        predicted_stops = [AnnotatedStop(datetime.utcfromtimestamp(25), datetime.utcfromtimestamp(30))]

        metric = self.test_file.get_metrics(predicted_stops)
        self.assertEqual(metric.tp, 1)
        self.assertEqual(metric.fp, 0)
        self.assertEqual(metric.fn, 1)

    def test_recall_correct(self):
        predicted_stops = [
            AnnotatedStop(datetime.utcfromtimestamp(0), datetime.utcfromtimestamp(5)),
            AnnotatedStop(datetime.utcfromtimestamp(10), datetime.utcfromtimestamp(15)),
            AnnotatedStop(datetime.utcfromtimestamp(25), datetime.utcfromtimestamp(30)),
        ]

        metric = self.test_file.get_metrics(predicted_stops)
        self.assertEqual(metric.tp, 2)
        self.assertEqual(metric.fp, 1)
        self.assertEqual(metric.fn, 0)


class TestAnnotatedStop(TestCase):
    def test_max_margin(self):
        as1 = AnnotatedStop(datetime.fromtimestamp(1), datetime.fromtimestamp(10))
        as2 = AnnotatedStop(datetime.fromtimestamp(5), datetime.fromtimestamp(15))

        overlap = as1.overlap_percent(as2)
        self.assertAlmostEqual(overlap, 0.5555, places=3)

    def test_max_margin_non_overlap(self):
        as1 = AnnotatedStop(datetime.fromtimestamp(1), datetime.fromtimestamp(10))
        as2 = AnnotatedStop(datetime.fromtimestamp(11), datetime.fromtimestamp(15))

        overlap = as1.overlap_percent(as2)
        self.assertAlmostEqual(overlap, -0.25, places=3)


if __name__ == "__main__":
    main()
