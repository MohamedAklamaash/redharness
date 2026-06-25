"""Dataset loaders. Importing this package registers the bundled demo dataset."""

from redharness.datasets.demo import DemoDataset
from redharness.datasets.leakage import LeakageDataset
from redharness.datasets.remote import RemoteDataset
from redharness.datasets.strongreject import StrongRejectDataset

__all__ = ["DemoDataset", "LeakageDataset", "RemoteDataset", "StrongRejectDataset"]
