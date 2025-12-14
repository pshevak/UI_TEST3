"""
Model loader and prediction module for reburn risk prediction.

This module loads the trained Random Forest model and provides functions
to predict reburn risk for fires using their fire_id.
"""

from __future__ import annotations

import os
import joblib
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Paths relative to this file's directory (reburn/)
REBURN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(REBURN_DIR, ".."))

# Model and data paths - model is in reburn/, JSON data is in data/
MODEL_PATH = os.path.join(REBURN_DIR, "rf_model.joblib")
DATA_JSON_PATH = os.path.join(PROJECT_ROOT, "data", "fires_master.json")
SUMMARY_PATH = os.path.join(REBURN_DIR, "summary.json")

# Global variables for lazy loading
_model = None
_fire_data = None
_fire_lookup = None
_summary = None


def load_model() -> object:
    """Load the trained Random Forest model from disk."""
    global _model
    if _model is None:
        # Compatibility shim: some saved pipelines (numpy>=2) reference numpy._core
        # which doesn't exist on numpy 1.x. Map it to numpy.core so unpickling works.
        import types, sys as _sys
        if "numpy._core" not in _sys.modules:
            _sys.modules["numpy._core"] = types.ModuleType("numpy._core")
            _sys.modules["numpy._core"].__dict__.update(np.core.__dict__)

        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model file not found: {MODEL_PATH}\n"
                "Please train the model first using: python3 reburn/train_random_forest.py"
            )
        _model = joblib.load(MODEL_PATH)
    return _model


def load_fire_data() -> Tuple[List[Dict], Dict[str, Dict]]:
    """Load the JSON dataset for feature lookup."""
    global _fire_data, _fire_lookup
    if _fire_data is None:
        if not os.path.exists(DATA_JSON_PATH):
            raise FileNotFoundError(
                f"Data file not found: {DATA_JSON_PATH}\n"
                "Please ensure data/fires_master.json exists in the project."
            )
        with open(DATA_JSON_PATH, "r") as f:
            _fire_data = json.load(f)
        # Create lookup by fire_id for faster access
        _fire_lookup = {}
        for fire in _fire_data:
            fire_id = fire.get("fire_id") or fire.get("id")
            if fire_id:
                _fire_lookup[fire_id] = fire
    return _fire_data, _fire_lookup


def load_data_as_dataframe() -> pd.DataFrame:
    """Load the JSON dataset as a pandas DataFrame (for training compatibility)."""
    fire_data, _ = load_fire_data()
    df = pd.DataFrame(fire_data)
    # Ensure fire_id column exists and set as index
    if "fire_id" not in df.columns and "id" in df.columns:
        df["fire_id"] = df["id"]
    df.set_index("fire_id", inplace=True, drop=False)
    return df


def load_summary() -> Dict:
    """Load the model summary JSON for metadata."""
    global _summary
    if _summary is None:
        if not os.path.exists(SUMMARY_PATH):
            raise FileNotFoundError(
                f"Summary file not found: {SUMMARY_PATH}"
            )
        with open(SUMMARY_PATH, "r") as f:
            _summary = json.load(f)
    return _summary


def get_fire_features(fire_id: str) -> Optional[Dict]:
    """
    Get feature dict for a given fire_id from the JSON data.
    
    Args:
        fire_id: The fire identifier (e.g., "ca3617411872220040812")
        
    Returns:
        Dictionary with all fire features, or None if fire_id not found
    """
    _, fire_lookup = load_fire_data()
    return fire_lookup.get(fire_id)


def predict_reburn_risk(
    fire_id: str,
    return_confidence: bool = True
) -> Dict:
    """
    Predict reburn risk for a given fire_id.
    
    Args:
        fire_id: The fire identifier (e.g., "ca3617411872220040812")
        return_confidence: If True, include confidence score in response
        
    Returns:
        Dictionary with prediction results:
        {
            "reburn_probability": float,  # Probability of reburn (0-1)
            "reburn_prediction": bool,    # Binary prediction
            "risk_level": str,            # "High", "Medium", or "Low"
            "confidence": float,          # Confidence score (if requested)
            "fire_id": str,
            "model_version": str,
            "features_used": dict,        # The features used for prediction
        }
        
    Raises:
        FileNotFoundError: If model or data file not found
        ValueError: If fire_id not found in dataset
    """
    # Load model and data
    model = load_model()
    fire_features = get_fire_features(fire_id)
    
    if fire_features is None:
        raise ValueError(
            f"Fire ID '{fire_id}' not found in dataset. "
            f"Please check the fire_id and ensure it exists in data/fires_master.json"
        )
    
    # Extract features needed for prediction
    # Based on summary.json, the model expects:
    # Numeric: elevation_m, avg_temp_c, soil_moisture_pct, gw_depth_ft, ph_val, precip_mm, land_burned_frequency
    # Categorical: state
    
    # Create a DataFrame with the fire's features (model expects DataFrame input)
    feature_df = pd.DataFrame([fire_features])
    
    # Predict
    reburn_probability = model.predict_proba(feature_df)[0, 1]  # Probability of class 1 (reburn)
    reburn_prediction = model.predict(feature_df)[0] == 1  # Binary prediction
    
    # Determine risk level based on probability
    if reburn_probability >= 0.7:
        risk_level = "High"
    elif reburn_probability >= 0.4:
        risk_level = "Medium"
    else:
        risk_level = "Low"
    
    # Calculate confidence (distance from 0.5 threshold)
    confidence = abs(reburn_probability - 0.5) * 2  # Scale to 0-1
    
    # Get model version from summary
    try:
        summary = load_summary()
        model_version = summary.get("task", "reburn_risk_prediction")
    except:
        model_version = "reburn_risk_prediction"
    
    # Extract features used for prediction
    features_used = {
        "elevation_m": float(fire_features.get("elevation_m", 0) or 0),
        "avg_temp_c": float(fire_features.get("avg_temp_c", 0) or 0),
        "soil_moisture_pct": float(fire_features.get("soil_moisture_pct", 0) or 0),
        "gw_depth_ft": float(fire_features.get("gw_depth_ft", 0) or 0),
        "ph_val": float(fire_features.get("ph_val", 0) or 0),
        "precip_mm": float(fire_features.get("precip_mm", 0) or 0),
        "land_burned_frequency": int(fire_features.get("land_burned_frequency", 0) or 0),
        "state": str(fire_features.get("state", "")),
    }
    
    result = {
        "reburn_probability": round(reburn_probability, 4),
        "reburn_prediction": bool(reburn_prediction),
        "risk_level": risk_level,
        "fire_id": fire_id,
        "model_version": model_version,
        "features_used": features_used,
    }
    
    if return_confidence:
        result["confidence"] = round(confidence, 4)
    
    return result


def predict_reburn_risk_from_features(
    features: Dict,
    return_confidence: bool = True
) -> Dict:
    """
    Predict reburn risk from direct feature input (alternative to fire_id lookup).
    
    Args:
        features: Dictionary with feature values:
            - elevation_m: float
            - avg_temp_c: float
            - soil_moisture_pct: float
            - gw_depth_ft: float
            - ph_val: float
            - precip_mm: float
            - land_burned_frequency: int
            - state: str (e.g., "CA")
        return_confidence: If True, include confidence score in response
        
    Returns:
        Dictionary with prediction results (same format as predict_reburn_risk)
    """
    model = load_model()
    
    # Create DataFrame from features
    feature_df = pd.DataFrame([features])
    
    # Predict
    reburn_probability = model.predict_proba(feature_df)[0, 1]
    reburn_prediction = model.predict(feature_df)[0] == 1
    
    # Determine risk level
    if reburn_probability >= 0.7:
        risk_level = "High"
    elif reburn_probability >= 0.4:
        risk_level = "Medium"
    else:
        risk_level = "Low"
    
    confidence = abs(reburn_probability - 0.5) * 2
    
    try:
        summary = load_summary()
        model_version = summary.get("task", "reburn_risk_prediction")
    except:
        model_version = "reburn_risk_prediction"
    
    result = {
        "reburn_probability": round(reburn_probability, 4),
        "reburn_prediction": bool(reburn_prediction),
        "risk_level": risk_level,
        "model_version": model_version,
        "features_used": features,
    }
    
    if return_confidence:
        result["confidence"] = round(confidence, 4)
    
    return result
