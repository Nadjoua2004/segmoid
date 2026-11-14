import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assistant.data_provider import MockDataProvider  # noqa: E402


class FakeKB:
    backend = "fake"
    size = 3

    def __init__(self):
        self.queries = []

    def search(self, query, k=4, kind=None):
        self.queries.append(query)
        return [
            {"id": "a", "title": "NASA-STD-3001 Technical Brief - Radiation Protection", "url": "https://nasa.gov/rad.pdf",
             "page": 2, "text": "Crew should shelter in the most shielded area during a solar particle event.", "score": 0.8},
            {"id": "b", "title": "NASA - The Human Body in Space", "url": "https://nasa.gov/body",
             "page": None, "text": "Sleep loss and circadian misalignment degrade performance in space.", "score": 0.6},
            {"id": "c", "title": "NASA - Astronaut Exercise", "url": "https://nasa.gov/ex",
             "page": None, "text": "Astronauts exercise about two hours a day to counter deconditioning.", "score": 0.4},
        ][:k]


@pytest.fixture
def provider():
    return MockDataProvider(day=47)


@pytest.fixture
def kb():
    return FakeKB()
