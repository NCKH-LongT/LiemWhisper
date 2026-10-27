import sys
from pathlib import Path
import pytest

torch = pytest.importorskip("torch")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from liemwhisper.alignment import retrieval_topk, symmetric_info_nce


def test_retrieval_identity():
    x = torch.eye(3)
    assert retrieval_topk(x, x, k=1).squeeze(1).tolist() == [0, 1, 2]


def test_contrastive_loss_is_finite_and_has_gradient():
    x = torch.eye(3, requires_grad=True)
    y = torch.eye(3)
    loss = symmetric_info_nce(x, y)
    assert torch.isfinite(loss)
    loss.backward()
    assert x.grad is not None
