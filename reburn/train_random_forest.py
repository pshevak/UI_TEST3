"""
Train a Random Forest classifier to predict future reburn risk (`reburn` column)
from the master dataset. This script is standalone and does NOT integrate with 
the FastAPI backend. It reads the JSON data, performs grouped splits by `fire_id` to 
avoid leakage, trains with cross-validated hyperparameters, and emits metrics 
and plots for binary classification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Tuple, Dict, Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    roc_auc_score,
    roc_curve,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.model_selection import GridSearchCV, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def load_data(data_path: Path) -> pd.DataFrame:
    """Load JSON data and convert to DataFrame, dropping rows without reburn labels."""
    with open(data_path, "r") as f:
        fire_data = json.load(f)
    
    df = pd.DataFrame(fire_data)
    
    # Ensure fire_id column exists
    if "fire_id" not in df.columns and "id" in df.columns:
        df["fire_id"] = df["id"]
    
    # Drop rows without reburn labels
    df = df.dropna(subset=["reburn"])
    
    # Convert reburn to int (0/1) for sklearn
    # Handle various formats: bool, string "True"/"False", etc.
    if df["reburn"].dtype == object:
        df["reburn"] = df["reburn"].map({"True": True, "False": False, "true": True, "false": False, True: True, False: False})
    df["reburn"] = df["reburn"].astype(int)
    
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare features for training - using raw features directly (no engineering)."""
    # Just return a copy - Random Forest works best with raw continuous features
    return df.copy()


def split_groups(
    df: pd.DataFrame, group_col: str, test_size: float = 0.15, val_size: float = 0.15, random_state: int = 42
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return indices for train/val/test grouped by group_col to avoid data leakage."""
    groups = df[group_col]
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_val_idx, test_idx = next(gss.split(df, groups=groups))

    # Further split train_val into train and val
    remaining_df = df.iloc[train_val_idx]
    remaining_groups = remaining_df[group_col]
    val_prop = val_size / (1 - test_size)
    gss_val = GroupShuffleSplit(n_splits=1, test_size=val_prop, random_state=random_state + 1)
    train_idx_rel, val_idx_rel = next(gss_val.split(remaining_df, groups=remaining_groups))

    train_idx = remaining_df.iloc[train_idx_rel].index.values
    val_idx = remaining_df.iloc[val_idx_rel].index.values

    return train_idx, val_idx, test_idx


def select_feature_sets(df: pd.DataFrame, exclude_burn_frequency: bool = False) -> Tuple[List[str], List[str], List[str]]:
    """Select raw features directly - Random Forest handles continuous features best."""
    # Raw numeric features (continuous) - RF learns optimal thresholds automatically
    numeric_candidates = [
        "elevation_m",
        "avg_temp_c",
        "annual_precip_mm",
        "soil_moisture_pct",
        "gw_depth_ft",
        "ph_val",
        "precip_mm",
        "land_burned_frequency",  # CRITICAL: Most important feature (72% importance)
        "acres",
    ]
    
    # Remove land_burned_frequency if requested
    if exclude_burn_frequency:
        numeric_candidates = [f for f in numeric_candidates if f != "land_burned_frequency"]
    
    # Categorical features (only state - keep as categorical)
    categorical_candidates = [
        "state",
    ]
    
    # No binary features - using raw continuous values instead

    def keep_if_present_and_not_all_nan(cols: List[str]) -> List[str]:
        kept = []
        for c in cols:
            if c in df.columns:
                series = df[c]
                if not series.isna().all():
                    kept.append(c)
        return kept

    numeric_features = keep_if_present_and_not_all_nan(numeric_candidates)
    categorical_features = keep_if_present_and_not_all_nan(categorical_candidates)
    binary_features = []  # No binary features - using raw continuous values

    return numeric_features, categorical_features, binary_features


def build_pipeline(
    numeric_features: List[str],
    categorical_features: List[str],
    binary_features: List[str],
    n_estimators: int = 300,
    max_depth=None,
    min_samples_leaf: int = 2,
) -> Pipeline:
    """
    Build the RF pipeline for binary reburn risk classification using raw features.
    Uses balanced class weights to handle the slight class imbalance.
    """
    transformers = []
    if numeric_features:
        transformers.append(
            ("num", Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]), numeric_features)
        )
    if categorical_features:
        transformers.append(
            ("cat", Pipeline(steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")), 
                ("onehot", OneHotEncoder(handle_unknown="ignore"))
            ]), categorical_features)
        )
    # Note: binary_features list will be empty since we're using raw continuous features

    preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight="balanced",  # Handle class imbalance (309 True vs 191 False)
        random_state=42,
        n_jobs=-1,
    )

    model = Pipeline(steps=[("preprocess", preprocessor), ("rf", clf)])
    return model


def tune_hyperparams(X, y, groups, pipeline: Pipeline) -> Tuple[Pipeline, Dict[str, Any]]:
    """Perform GridSearchCV with grouped cross-validation for reburn prediction."""
    param_grid = {
        "rf__n_estimators": [200, 400, 600],
        "rf__max_depth": [None, 10, 20, 30],
        "rf__min_samples_leaf": [1, 2, 4],
    }
    gss = GroupShuffleSplit(n_splits=3, test_size=0.2, random_state=42)
    search = GridSearchCV(
        pipeline,
        param_grid=param_grid,
        cv=gss.split(X, y, groups=groups),
        scoring="roc_auc",  # Use ROC-AUC for binary classification
        n_jobs=-1,
        verbose=1,
    )
    search.fit(X, y)
    print(f"Best params: {search.best_params_}")
    print(f"Best CV ROC-AUC: {search.best_score_:.4f}")
    return search.best_estimator_, search.best_params_


def evaluate(model: Pipeline, X, y_true, split_name: str, out_dir: Path) -> Dict[str, float]:
    """Evaluate model with binary classification metrics."""
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)[:, 1]  # Probability of reburn (class 1)

    # Calculate metrics
    acc = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_true, y_proba)

    print(f"\n[{split_name}] Metrics:")
    print(f"  Accuracy:  {acc:.4f}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  F1-Score:  {f1:.4f}")
    print(f"  ROC-AUC:   {roc_auc:.4f}")
    print(f"\n[{split_name}] Classification Report:\n{classification_report(y_true, y_pred, target_names=['No Reburn', 'Reburn'])}")

    # Confusion matrix plot
    labels = [0, 1]
    cm = confusion_matrix(y_true, y_pred, labels=labels, normalize="true")
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["No Reburn", "Reburn"])
    disp.plot(cmap="Blues", values_format=".2f")
    plt.title(f"Reburn Risk Confusion Matrix ({split_name})")
    out_path = out_dir / f"confusion_matrix_{split_name.lower()}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"Saved confusion matrix to {out_path}")

    return {
        "accuracy": acc,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "roc_auc": roc_auc,
    }


def plot_roc_curve(model: Pipeline, X_test, y_test, out_dir: Path):
    """Plot ROC curve for the test set."""
    y_proba = model.predict_proba(X_test)[:, 1]
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_auc = roc_auc_score(y_test, y_proba)

    plt.figure(figsize=(8, 6))
    plt.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC curve (AUC = {roc_auc:.3f})")
    plt.plot([0, 1], [0, 1], color="navy", lw=2, linestyle="--", label="Random classifier")
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curve - Reburn Risk Prediction")
    plt.legend(loc="lower right")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    out_path = out_dir / "roc_curve.png"
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"Saved ROC curve to {out_path}")


def plot_feature_importance(model: Pipeline, out_dir: Path):
    """Plot top 20 feature importances."""
    rf: RandomForestClassifier = model.named_steps["rf"]
    pre: ColumnTransformer = model.named_steps["preprocess"]
    feature_names = []

    # Extract feature names from each transformer
    for name, transformer, cols in pre.transformers_:
        if name == "num":
            feature_names.extend(cols)
        elif name == "cat":
            cat_encoder: OneHotEncoder = transformer.named_steps["onehot"]
            feature_names.extend(cat_encoder.get_feature_names_out())
        elif name == "bin":
            feature_names.extend(cols)

    feature_names = np.array(feature_names)
    importances = rf.feature_importances_

    # Get top features (up to 20 or all if fewer)
    n_features = min(20, len(feature_names))
    idx = np.argsort(importances)[::-1][:n_features]
    top_features = feature_names[idx]
    top_values = importances[idx]

    plt.figure(figsize=(10, 8))
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(top_features)))
    plt.barh(range(len(top_features)), top_values[::-1], color=colors[::-1])
    plt.yticks(range(len(top_features)), top_features[::-1])
    plt.xlabel("Feature Importance")
    plt.ylabel("Feature")
    plt.title("Random Forest Feature Importance for Reburn Risk Prediction")
    plt.tight_layout()
    out_path = out_dir / "feature_importance_top20.png"
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"Saved feature importance plot to {out_path}")

    return dict(zip(top_features.tolist(), top_values.tolist()))


def plot_class_distribution(y_train, y_val, y_test, out_dir: Path):
    """Plot class distribution across splits."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    
    splits = [("Train", y_train), ("Validation", y_val), ("Test", y_test)]
    
    for ax, (name, y) in zip(axes, splits):
        counts = pd.Series(y).value_counts().sort_index()
        colors = ["#2ecc71", "#e74c3c"]  # Green for no reburn, red for reburn
        ax.bar(["No Reburn", "Reburn"], [counts.get(0, 0), counts.get(1, 0)], color=colors)
        ax.set_title(f"{name} Set (n={len(y)})")
        ax.set_ylabel("Count")
        for i, v in enumerate([counts.get(0, 0), counts.get(1, 0)]):
            ax.text(i, v + 1, str(v), ha="center", fontweight="bold")
    
    plt.suptitle("Reburn Class Distribution Across Splits", fontsize=14)
    plt.tight_layout()
    out_path = out_dir / "class_distribution.png"
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"Saved class distribution plot to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Train Random Forest for reburn risk prediction.")
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent
    
    parser.add_argument(
        "--data", 
        type=Path, 
        default=project_root / "data" / "fires_master.json", 
        help="Path to master dataset JSON file"
    )
    parser.add_argument(
        "--out", 
        type=Path, 
        default=script_dir,  # Output to reburn/ directory
        help="Directory to save artifacts"
    )
    parser.add_argument(
        "--skip-tuning", 
        action="store_true", 
        help="Skip hyperparameter tuning and use defaults"
    )
    parser.add_argument(
        "--exclude-burn-freq",
        action="store_true",
        help="[TESTING ONLY] Exclude land_burned_frequency feature. WARNING: This dramatically reduces performance."
    )
    args = parser.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("REBURN RISK PREDICTION - Random Forest Classifier")
    if args.exclude_burn_freq:
        print("MODE: Environmental features only (excluding land_burned_frequency)")
    print("=" * 60)

    # Load and prepare data
    print(f"\nLoading data from {args.data}...")
    df = load_data(args.data)
    df = prepare_features(df)  # Using raw features directly

    target = "reburn"
    group_col = "fire_id"

    print(f"Total samples: {len(df)}")
    print(f"Reburn distribution: {df[target].value_counts().to_dict()}")

    # Split data
    train_idx, val_idx, test_idx = split_groups(df, group_col=group_col)

    X = df.drop(columns=[target])
    y = df[target]

    # Select features
    numeric_features, categorical_features, binary_features = select_feature_sets(df, exclude_burn_frequency=args.exclude_burn_freq)
    print(f"\nNumeric features: {numeric_features}")
    print(f"Categorical features: {categorical_features}")
    print(f"Binary features: {binary_features}")

    # Plot class distribution
    plot_class_distribution(
        y.iloc[train_idx].values, 
        y.iloc[val_idx].values, 
        y.iloc[test_idx].values, 
        out_dir
    )

    # Build and train model
    base_model = build_pipeline(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        binary_features=binary_features,
    )

    best_params = {}
    if args.skip_tuning:
        print("\nTraining with default parameters...")
        model = base_model.fit(X.iloc[train_idx], y.iloc[train_idx])
    else:
        print("\nPerforming hyperparameter tuning...")
        model, best_params = tune_hyperparams(
            X.iloc[train_idx], 
            y.iloc[train_idx], 
            df.iloc[train_idx][group_col], 
            base_model
        )

    # Evaluate on all splits
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    
    train_metrics = evaluate(model, X.iloc[train_idx], y.iloc[train_idx], "Train", out_dir)
    val_metrics = evaluate(model, X.iloc[val_idx], y.iloc[val_idx], "Val", out_dir)
    test_metrics = evaluate(model, X.iloc[test_idx], y.iloc[test_idx], "Test", out_dir)

    # Plot ROC curve for test set
    plot_roc_curve(model, X.iloc[test_idx], y.iloc[test_idx], out_dir)

    # Feature importance
    feature_importance = plot_feature_importance(model, out_dir)

    # Save model
    model_path = out_dir / "rf_model.joblib"
    try:
        import joblib
        joblib.dump(model, model_path)
        print(f"\nSaved model to {model_path}")
    except Exception as e:
        print(f"Could not save model: {e}")

    # Save comprehensive summary
    summary = {
        "task": "reburn_risk_prediction",
        "target_column": "reburn",
        "total_samples": len(df),
        "class_distribution": {
            "no_reburn": int((df[target] == 0).sum()),
            "reburn": int((df[target] == 1).sum()),
        },
        "splits": {
            "train_size": len(train_idx),
            "val_size": len(val_idx),
            "test_size": len(test_idx),
        },
        "features": {
            "numeric": numeric_features,
            "categorical": categorical_features,
            "binary": binary_features,
        },
        "best_hyperparameters": best_params,
        "metrics": {
            "train": train_metrics,
            "validation": val_metrics,
            "test": test_metrics,
        },
        "top_features": feature_importance,
    }
    
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved summary to {out_dir / 'summary.json'}")

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print(f"Test ROC-AUC: {test_metrics['roc_auc']:.4f}")
    print(f"Test F1-Score: {test_metrics['f1_score']:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
