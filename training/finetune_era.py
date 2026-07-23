#!/usr/bin/env python3
"""Fine-tune Maia-2 on an era corpus.

    python training/finetune_era.py romantic --epochs 2 --lr 1e-5

Runs on GPU if available (Colab T4 is plenty: ~750k positions/era, minutes-to-
low-hours per era), CPU works overnight for small runs. Needs:
    pip install maia2 torch

Reads  data/training/{era}.pkl   (from scripts/prepare_training.py)
Writes models/{era}.pt           (state_dict; load per backend/engines.py)
Also writes models/{era}.meta.json with held-out move-match accuracy.
"""
import argparse
import json
import pickle
import random
from pathlib import Path
from types import SimpleNamespace

import torch
import torch.nn.functional as F

from maia2 import model as maia2_model
from maia2.main import MAIA2Dataset
from maia2.utils import get_all_possible_moves

ROOT = Path(__file__).resolve().parent.parent


def evaluate(net, loader, device):
    net.eval()
    correct = total = 0
    with torch.no_grad():
        for boards, labels, elos_self, elos_oppo, _wdl in loader:
            boards, labels = boards.to(device), labels.to(device)
            logits, _side, _value = net(boards, elos_self.to(device), elos_oppo.to(device))
            correct += (logits.argmax(dim=1) == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def main(era, epochs, lr, batch_size, holdout, seed, device_arg):
    device = torch.device(device_arg if device_arg else ("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"Device: {device}")

    rows = pickle.load(open(ROOT / "data" / "training" / f"{era}.pkl", "rb"))
    random.seed(seed)
    random.shuffle(rows)
    n_hold = int(len(rows) * holdout)
    train_rows, hold_rows = rows[n_hold:], rows[:n_hold]
    print(f"{era}: {len(train_rows)} train / {len(hold_rows)} held-out positions")

    all_moves_dict = {m: i for i, m in enumerate(get_all_possible_moves())}
    cfg = SimpleNamespace(side_info=False)
    mk_loader = lambda data, shuffle: torch.utils.data.DataLoader(
        MAIA2Dataset(data, all_moves_dict, cfg), batch_size=batch_size,
        shuffle=shuffle, num_workers=2)
    train_loader, hold_loader = mk_loader(train_rows, True), mk_loader(hold_rows, False)

    net = maia2_model.from_pretrained(type="rapid", device="gpu" if device.type == "cuda" else "cpu")
    net = net.to(device)

    base_acc = evaluate(net, hold_loader, device)
    print(f"Pre-finetune held-out accuracy: {base_acc:.3f}")

    opt = torch.optim.AdamW(net.parameters(), lr=lr)
    for epoch in range(epochs):
        net.train()
        running, steps = 0.0, 0
        for boards, labels, elos_self, elos_oppo, _wdl in train_loader:
            boards, labels = boards.to(device), labels.to(device)
            logits, _side, _value = net(boards, elos_self.to(device), elos_oppo.to(device))
            loss = F.cross_entropy(logits, labels)
            opt.zero_grad()
            loss.backward()
            opt.step()
            running += loss.item()
            steps += 1
            if steps % 200 == 0:
                print(f"  epoch {epoch+1} step {steps}: loss {running/steps:.4f}")
        acc = evaluate(net, hold_loader, device)
        print(f"Epoch {epoch+1}: train loss {running/max(steps,1):.4f}, held-out acc {acc:.3f}")

    out = ROOT / "models" / f"{era}.pt"
    out.parent.mkdir(exist_ok=True)
    torch.save(net.state_dict(), out)
    json.dump({"era": era, "epochs": epochs, "lr": lr, "positions": len(train_rows),
               "base_acc": base_acc, "final_acc": acc},
              open(ROOT / "models" / f"{era}.meta.json", "w"), indent=2)
    print(f"Saved {out}")
    print("Gate check: final_acc should beat base_acc — the model now predicts")
    print("this era's moves better than generic Maia-2. Then run scripts/sanity_gate.py.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    import yaml
    eras = list(yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())["eras"])
    p.add_argument("era", choices=eras)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--batch-size", type=int, default=512)
    p.add_argument("--holdout", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default=None, help="cuda / cpu (default: auto)")
    a = p.parse_args()
    main(a.era, a.epochs, a.lr, a.batch_size, a.holdout, a.seed, a.device)
