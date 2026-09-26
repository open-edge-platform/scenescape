#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fine-tune RadarPillars on VIDETEC with NaN / empty-batch guards.

Attempt-1 evidence: ep5 finite and useful; ep10+ had NaN in 116/118 tensors
(empty preds). This trainer skips non-finite loss, skips forward failures
(empty-pillar batches), aborts if weights go non-finite, and does **not**
auto-resume a prior run (pass ``--resume`` explicitly).
"""

from __future__ import annotations

import argparse
import datetime
import glob
import os
import sys
from pathlib import Path

import torch
from torch.nn.utils import clip_grad_norm_
import tqdm

_orig_load = torch.load


def _torch_load(*args, **kwargs):
  kwargs.setdefault("weights_only", False)
  return _orig_load(*args, **kwargs)


torch.load = _torch_load

RP = Path("/home/spoluri/mainline/RadarPillar")
os.chdir(RP)
sys.path.insert(0, str(RP))
sys.path.insert(0, str(RP / "tools"))

from tensorboardX import SummaryWriter  # noqa: E402

from pcdet.config import cfg, cfg_from_yaml_file, log_config_to_file  # noqa: E402
from pcdet.datasets import build_dataloader  # noqa: E402
from pcdet.models import build_network, model_fn_decorator  # noqa: E402
from pcdet.utils import common_utils  # noqa: E402
from train_utils.optimization import build_optimizer, build_scheduler  # noqa: E402


def _model_has_nonfinite(model) -> list[str]:
  bad = []
  for name, p in model.named_parameters():
    if p is None or not p.is_floating_point():
      continue
    if torch.isnan(p).any() or torch.isinf(p).any():
      bad.append(name)
  return bad


def _snapshot_bn(model):
  snap = {}
  for name, mod in model.named_modules():
    if isinstance(mod, (torch.nn.BatchNorm1d, torch.nn.BatchNorm2d,
                        torch.nn.BatchNorm3d, torch.nn.SyncBatchNorm)):
      snap[name] = {
        "running_mean": mod.running_mean.detach().clone() if mod.running_mean is not None else None,
        "running_var": mod.running_var.detach().clone() if mod.running_var is not None else None,
        "num_batches_tracked": (
          mod.num_batches_tracked.detach().clone()
          if getattr(mod, "num_batches_tracked", None) is not None else None),
      }
  return snap


def _restore_bn(model, snap):
  for name, mod in model.named_modules():
    if name not in snap:
      continue
    s = snap[name]
    if s["running_mean"] is not None and mod.running_mean is not None:
      mod.running_mean.copy_(s["running_mean"])
    if s["running_var"] is not None and mod.running_var is not None:
      mod.running_var.copy_(s["running_var"])
    if s["num_batches_tracked"] is not None and getattr(mod, "num_batches_tracked", None) is not None:
      mod.num_batches_tracked.copy_(s["num_batches_tracked"])


def _save_ckpt(model, optimizer, epoch, it, ckpt_dir, logger, max_keep: int):
  path = ckpt_dir / f"checkpoint_epoch_{epoch}.pth"
  state = {
    "epoch": epoch,
    "it": it,
    "model_state": model.state_dict(),
    "optimizer_state": optimizer.state_dict(),
    "version": "videtec_gantry_ft_guarded",
  }
  torch.save(state, path)
  logger.info("saved %s", path)
  ckpts = sorted(ckpt_dir.glob("checkpoint_epoch_*.pth"), key=os.path.getmtime)
  while len(ckpts) > max_keep:
    old = ckpts.pop(0)
    old.unlink(missing_ok=True)


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--cfg_file", default="tools/cfgs/vod_models/videtec_radarpillar_gantry.yaml")
  ap.add_argument("--batch_size", type=int, default=4)
  ap.add_argument("--epochs", type=int, default=12)
  ap.add_argument("--workers", type=int, default=4)
  ap.add_argument("--extra_tag", default="videtec_gantry_ft2")
  ap.add_argument("--pretrained_model",
                  default="weights/radarpillar_vod_best_map52.56.pth")
  ap.add_argument("--resume", type=Path, default=None,
                  help="Optional ckpt to resume; default starts fresh from pretrained")
  ap.add_argument("--ckpt_save_interval", type=int, default=1)
  ap.add_argument("--max_ckpt_save_num", type=int, default=15)
  ap.add_argument("--lr", type=float, default=None, help="Override OPTIMIZATION.LR")
  ap.add_argument("--freeze-backbone-3d", action="store_true", default=True,
                  help="Freeze PillarAttention (nan-grad source on associated VIDETEC); default on")
  ap.add_argument("--no-freeze-backbone-3d", action="store_false", dest="freeze_backbone_3d")
  args = ap.parse_args()

  cfg_from_yaml_file(args.cfg_file, cfg)
  cfg.TAG = Path(args.cfg_file).stem
  cfg.EXP_GROUP_PATH = "/".join(Path(args.cfg_file).parts[1:-1])
  cfg.LOCAL_RANK = 0
  if args.lr is not None:
    cfg.OPTIMIZATION.LR = float(args.lr)

  common_utils.set_random_seed(666)

  output_dir = cfg.ROOT_DIR / "output" / cfg.EXP_GROUP_PATH / cfg.TAG / args.extra_tag
  ckpt_dir = output_dir / "ckpt"
  output_dir.mkdir(parents=True, exist_ok=True)
  ckpt_dir.mkdir(parents=True, exist_ok=True)

  log_file = output_dir / ("log_train_%s.txt" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
  logger = common_utils.create_logger(log_file, rank=0)
  logger.info("**********************Start logging (NaN-guarded)**********************")
  for key, val in vars(args).items():
    logger.info("{:16} {}".format(key, val))
  log_config_to_file(cfg, logger=logger)
  os.system("cp %s %s" % (args.cfg_file, output_dir))

  tb_log = SummaryWriter(log_dir=str(output_dir / "tensorboard"))

  train_set, train_loader, train_sampler = build_dataloader(
    dataset_cfg=cfg.DATA_CONFIG,
    class_names=cfg.CLASS_NAMES,
    batch_size=args.batch_size,
    dist=False, workers=args.workers,
    logger=logger, training=True,
    total_epochs=args.epochs,
  )

  model = build_network(model_cfg=cfg.MODEL, num_class=len(cfg.CLASS_NAMES), dataset=train_set)
  model.cuda()

  start_epoch = 0
  it = 0
  last_epoch = -1
  if args.pretrained_model:
    model.load_params_from_file(filename=args.pretrained_model, to_cpu=False, logger=logger)

  if args.freeze_backbone_3d:
    n_frozen = 0
    for name, p in model.named_parameters():
      if name.startswith("backbone_3d"):
        p.requires_grad = False
        n_frozen += 1
    logger.info("Froze backbone_3d (%d tensors) — associated-set nan-grad mitigation", n_frozen)

  optimizer = build_optimizer(model, cfg.OPTIMIZATION)

  if args.resume is not None:
    it, start_epoch = model.load_params_with_optimizer(
      str(args.resume), to_cpu=False, optimizer=optimizer, logger=logger)
    last_epoch = start_epoch + 1
    bad = _model_has_nonfinite(model)
    if bad:
      raise SystemExit(f"refusing to resume non-finite weights ({len(bad)} tensors), e.g. {bad[:3]}")

  model.train()
  model_func = model_fn_decorator()
  lr_scheduler, lr_warmup_scheduler = build_scheduler(
    optimizer, total_iters_each_epoch=len(train_loader), total_epochs=args.epochs,
    last_epoch=last_epoch, optim_cfg=cfg.OPTIMIZATION)

  logger.info("**********************Start training**********************")
  n_skip_nan = 0
  n_skip_err = 0
  with tqdm.trange(start_epoch, args.epochs, desc="epochs", dynamic_ncols=True) as tbar:
    for epoch in tbar:
      if train_sampler is not None:
        train_sampler.set_epoch(epoch)
      dataloader_iter = iter(train_loader)
      pbar = tqdm.tqdm(total=len(train_loader), leave=False, desc="train", dynamic_ncols=True)
      epoch_loss_sum = 0.0
      epoch_steps = 0
      for _ in range(len(train_loader)):
        try:
          batch = next(dataloader_iter)
        except StopIteration:
          dataloader_iter = iter(train_loader)
          batch = next(dataloader_iter)

        try:
          cur_lr = float(optimizer.lr)
        except Exception:
          cur_lr = optimizer.param_groups[0]["lr"]

        model.train()
        optimizer.zero_grad()
        bn_snap = _snapshot_bn(model)
        try:
          loss, tb_dict, disp_dict = model_func(model, batch)
        except (RuntimeError, IndexError) as exc:
          n_skip_err += 1
          _restore_bn(model, bn_snap)
          logger.warning("skip forward error at it=%s: %s", it, exc)
          pbar.update()
          continue

        if not torch.isfinite(loss).all():
          n_skip_nan += 1
          # Forward already updated BN running stats — revert or they poison later steps.
          _restore_bn(model, bn_snap)
          logger.warning("skip non-finite loss at it=%s (BN restored)", it)
          optimizer.zero_grad()
          pbar.update()
          continue

        loss.backward()
        # Drop step if grads already non-finite
        grads_ok = True
        for p in model.parameters():
          if p.grad is not None and not torch.isfinite(p.grad).all():
            grads_ok = False
            break
        if not grads_ok:
          n_skip_nan += 1
          _restore_bn(model, bn_snap)
          logger.warning("skip non-finite grads at it=%s (BN restored)", it)
          optimizer.zero_grad()
          pbar.update()
          continue

        clip_grad_norm_(model.parameters(), cfg.OPTIMIZATION.GRAD_NORM_CLIP)
        optimizer.step()
        if lr_scheduler is not None:
          # OpenPCDet OneCycle passes accumulated iter
          try:
            lr_scheduler.step(it)
          except TypeError:
            lr_scheduler.step()

        it += 1
        epoch_loss_sum += float(loss.item())
        epoch_steps += 1
        disp_dict = dict(disp_dict or {})
        disp_dict.update({"loss": float(loss.item()), "lr": cur_lr,
                          "skip_nan": n_skip_nan, "skip_err": n_skip_err})
        pbar.update()
        tbar.set_postfix(disp_dict)
        if tb_log is not None:
          tb_log.add_scalar("train/loss", float(loss.item()), it)
          tb_log.add_scalar("meta_data/learning_rate", cur_lr, it)

      pbar.close()
      mean_loss = epoch_loss_sum / max(1, epoch_steps)
      logger.info("epoch %s mean_loss=%.4f steps=%s skip_nan=%s skip_err=%s",
                  epoch + 1, mean_loss, epoch_steps, n_skip_nan, n_skip_err)

      bad = _model_has_nonfinite(model)
      if bad:
        logger.error("NON-FINITE WEIGHTS after epoch %s (%d tensors), e.g. %s — aborting",
                     epoch + 1, len(bad), bad[:5])
        raise SystemExit(2)

      if (epoch + 1) % args.ckpt_save_interval == 0 or (epoch + 1) == args.epochs:
        _save_ckpt(model, optimizer, epoch + 1, it, ckpt_dir, logger, args.max_ckpt_save_num)

  logger.info("**********************End training**********************")
  print(f"ckpts → {ckpt_dir}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
