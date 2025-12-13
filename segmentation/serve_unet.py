#!/usr/bin/env python3
"""FastAPI inference service for the MTBS burn severity U-Net."""
from __future__ import annotations

import base64
import io
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio
import torch
import torch.nn as nn
import torch.nn.functional as F
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.transform import array_bounds

# ---------------------------------------------------------------------------
# Model + defaults
# ---------------------------------------------------------------------------

# Matches training config: default 12-channel input (pre + post) and 6 burn classes.
# We will detect required input channels from the checkpoint and adjust.
class UNet(nn.Module):
  def __init__(self, in_channels: int = 12, num_classes: int = 6, dropout_rate: float = 0.3):
    super().__init__()
    self.enc1 = self._conv_block(in_channels, 64, dropout_rate)
    self.enc2 = self._conv_block(64, 128, dropout_rate)
    self.enc3 = self._conv_block(128, 256, dropout_rate)
    self.enc4 = self._conv_block(256, 512, dropout_rate)
    self.bottleneck = self._conv_block(512, 1024, dropout_rate)
    self.upconv4 = nn.ConvTranspose2d(1024, 512, 2, stride=2)
    self.dec4 = self._conv_block(1024, 512, dropout_rate)
    self.upconv3 = nn.ConvTranspose2d(512, 256, 2, stride=2)
    self.dec3 = self._conv_block(512, 256, dropout_rate)
    self.upconv2 = nn.ConvTranspose2d(256, 128, 2, stride=2)
    self.dec2 = self._conv_block(256, 128, dropout_rate)
    self.upconv1 = nn.ConvTranspose2d(128, 64, 2, stride=2)
    self.dec1 = self._conv_block(128, 64, dropout_rate)
    self.final = nn.Conv2d(64, num_classes, 1)

  def _conv_block(self, in_channels: int, out_channels: int, dropout_rate: float) -> nn.Sequential:
    return nn.Sequential(
      nn.Conv2d(in_channels, out_channels, 3, padding=1),
      nn.BatchNorm2d(out_channels),
      nn.ReLU(inplace=True),
      nn.Dropout2d(dropout_rate),
      nn.Conv2d(out_channels, out_channels, 3, padding=1),
      nn.BatchNorm2d(out_channels),
      nn.ReLU(inplace=True),
      nn.Dropout2d(dropout_rate),
    )

  def forward(self, x: torch.Tensor) -> torch.Tensor:
    enc1 = self.enc1(x)
    enc2 = self.enc2(F.max_pool2d(enc1, 2))
    enc3 = self.enc3(F.max_pool2d(enc2, 2))
    enc4 = self.enc4(F.max_pool2d(enc3, 2))
    bottleneck = self.bottleneck(F.max_pool2d(enc4, 2))
    up4 = torch.cat([self.upconv4(bottleneck), enc4], dim=1)
    dec4 = self.dec4(up4)
    up3 = torch.cat([self.upconv3(dec4), enc3], dim=1)
    dec3 = self.dec3(up3)
    up2 = torch.cat([self.upconv2(dec3), enc2], dim=1)
    dec2 = self.dec2(up2)
    up1 = torch.cat([self.upconv1(dec2), enc1], dim=1)
    dec1 = self.dec1(up1)
    return self.final(dec1)


BURN_SEVERITY_COLORS: Dict[int, Tuple[int, int, int]] = {
  0: (34, 139, 34),   # Unburned
  1: (173, 216, 230), # Low
  2: (255, 255, 0),   # Moderate
  3: (255, 0, 0),     # High
  4: (144, 238, 144), # Increased Greenness
  5: (211, 211, 211)  # Non-Processing Area Mask
}

DEFAULT_MODEL_PATH = Path(os.environ.get("SEGMENTATION_MODEL_PATH", Path(__file__).with_name("best_model.pth")))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _load_state_dict(path: Path, device: torch.device) -> Dict[str, torch.Tensor]:
  if not path.is_file():
    raise FileNotFoundError(f"Checkpoint not found at {path}")
  return torch.load(path, map_location=device)


@lru_cache()
def get_model(model_path: Path = DEFAULT_MODEL_PATH, device: torch.device = DEVICE) -> nn.Module:
  state_dict = _load_state_dict(model_path, device)

  first_weight = state_dict.get("enc1.0.weight")
  if first_weight is None:
    raise RuntimeError("enc1.0.weight not found in checkpoint")
  in_channels = first_weight.shape[1]

  model = UNet(in_channels=in_channels, num_classes=6, dropout_rate=0.3).to(device)
  model.load_state_dict(state_dict)
  model.eval()
  return model


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _crop_to_stride(data: np.ndarray, stride: int = 16) -> np.ndarray:
  """Crop spatial dims to be divisible by stride to keep UNet skip shapes aligned."""
  _, h, w = data.shape
  new_h = (h // stride) * stride
  new_w = (w // stride) * stride
  return data[:, :new_h, :new_w]


def read_tif_to_tensor(raw_bytes: bytes, expected_channels: int) -> Tuple[torch.Tensor, Dict[str, Optional[object]]]:
  """Load a GeoTIFF from bytes and return a tensor shaped (1, C, H, W)."""
  with MemoryFile(raw_bytes) as memfile:
    with memfile.open() as src:
      data = src.read()  # (bands, H, W)
      transform = src.transform
      crs = src.crs.to_string() if src.crs else None

  channels = data.shape[0]
  if channels < expected_channels:
    raise HTTPException(status_code=400, detail=f"Expected at least {expected_channels} channels, found {channels}")

  data = data[:expected_channels].astype(np.float32)  # trim to expected
  data = _crop_to_stride(data, stride=16)
  _, height, width = data.shape
  data = data / 255.0  # match training normalization
  tensor = torch.from_numpy(data).unsqueeze(0)  # (1, 12, H, W)

  bounds = None
  if transform is not None:
    # array_bounds returns (minx, miny, maxx, maxy)
    _, h, w = data.shape
    min_x, min_y, max_x, max_y = array_bounds(h, w, transform)
    bounds = [[float(min_x), float(min_y)], [float(max_x), float(max_y)]]

  meta = {
    "width": width,
    "height": height,
    "bounds": bounds,
    "crs": crs,
  }
  return tensor, meta


def mask_to_png_bytes(mask: np.ndarray) -> bytes:
  """Convert class mask to a paletted PNG."""
  img = Image.fromarray(mask.astype(np.uint8), mode="P")
  palette = []
  for c in range(6):
    palette.extend(list(BURN_SEVERITY_COLORS[c]))
  # Pillow expects palette list length 768; pad remaining entries.
  palette.extend([0] * (768 - len(palette)))
  img.putpalette(palette)
  buf = io.BytesIO()
  img.save(buf, format="PNG")
  buf.seek(0)
  return buf.read()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Burn Severity Segmentation Service", version="0.1.0")


@app.get("/health")
async def health() -> Dict[str, str]:
  return {"status": "ok", "device": str(DEVICE), "model_path": str(DEFAULT_MODEL_PATH)}


@app.post("/predict")
async def predict_mask(tif: UploadFile = File(...), model_path: Optional[str] = None) -> JSONResponse:
  """Run segmentation on an uploaded GeoTIFF; expected band count is inferred from the checkpoint (e.g., 6-band post-only)."""
  if not tif.filename.lower().endswith((".tif", ".tiff")):
    raise HTTPException(status_code=400, detail="Only .tif/.tiff inputs are supported")

  raw = await tif.read()
  path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
  model = get_model(path, DEVICE)

  # Infer expected channels from the loaded model
  first_weight = next(model.parameters())
  expected_channels = first_weight.shape[1]

  tensor, meta = read_tif_to_tensor(raw, expected_channels)

  tensor = tensor.to(DEVICE)
  with torch.no_grad():
    logits = model(tensor)
    mask = torch.argmax(F.softmax(logits, dim=1), dim=1).squeeze(0).cpu().numpy()

  png_bytes = mask_to_png_bytes(mask)
  payload = {
    "mask_png_base64": base64.b64encode(png_bytes).decode("ascii"),
    "width": meta["width"],
    "height": meta["height"],
    "bounds": meta["bounds"],
    "crs": meta["crs"],
    "classes": list(BURN_SEVERITY_COLORS.keys()),
    "palette_rgb": BURN_SEVERITY_COLORS,
  }
  return JSONResponse(payload)


if __name__ == "__main__":
  import uvicorn
  uvicorn.run("segmentation.serve_unet:app", host="0.0.0.0", port=8002, reload=False)
