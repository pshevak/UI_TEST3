"""
Additional analysis and visualization script for Random Forest model results.
This script loads a trained model and generates supplementary plots for the results section.
Run this after training the model with train_random_forest.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.inspection import PartialDependenceDisplay
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import OneHotEncoder

# Import helper functions from train_random_forest.py
from train_random_forest import (
    prepare_features,
    load_data,
    select_feature_sets,
    split_groups,
)


def plot_per_class_metrics(y_true, y_pred, out_dir: Path, split_name: str = "Test"):
    """Plot precision, recall, and F1 per class as a grouped bar chart for reburn prediction."""
    labels = sorted(np.unique(y_true))
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )

    class_names = ["No Reburn", "Reburn"]
    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width, precision, width, label="Precision", alpha=0.8, color="#e74c3c")
    bars2 = ax.bar(x, recall, width, label="Recall", alpha=0.8, color="#3498db")
    bars3 = ax.bar(x + width, f1, width, label="F1-Score", alpha=0.8, color="#2ecc71")

    # Add value labels on bars
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{height:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xlabel("Reburn Class", fontsize=12)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title(f"Per-Class Performance Metrics ({split_name} Set)", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(class_names, rotation=0, ha="center")
    ax.legend(loc="upper right")
    ax.set_ylim([0, 1.15])
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)

    plt.tight_layout()
    out_path = out_dir / f"per_class_metrics_{split_name.lower()}.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved per-class metrics plot to {out_path}")


def plot_class_distribution(y_train, y_val, y_test, out_dir: Path):
    """Plot class distribution across train/val/test splits for reburn prediction."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    colors = ["#2ecc71", "#e74c3c"]  # Green for no reburn, red for reburn

    for ax, y, title in zip(axes, [y_train, y_val, y_test], ["Train", "Validation", "Test"]):
        counts = pd.Series(y).value_counts().sort_index()
        class_labels = ["No Reburn", "Reburn"]
        bars = ax.bar(
            class_labels,
            [counts.get(0, 0), counts.get(1, 0)],
            alpha=0.7,
            color=colors,
            edgecolor="black",
            linewidth=1.2,
        )

        # Add count labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )

        ax.set_title(f"{title} Set\n({len(y)} samples)", fontsize=12, fontweight="bold")
        ax.set_xlabel("Reburn Status", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

    plt.suptitle("Reburn Class Distribution Across Data Splits", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out_path = out_dir / "class_distribution.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved class distribution plot to {out_path}")


def get_feature_names_from_pipeline(model) -> List[str]:
    """Extract feature names from the preprocessing pipeline."""
    pre: ColumnTransformer = model.named_steps["preprocess"]
    feature_names = []

    for name, transformer, cols in pre.transformers_:
        if name == "num":
            feature_names.extend(cols)
        elif name == "cat":
            cat_encoder: OneHotEncoder = transformer.named_steps["onehot"]
            feature_names.extend(cat_encoder.get_feature_names_out())
        elif name == "bin":
            feature_names.extend(cols)

    return feature_names


def plot_partial_dependence(
    model, X_train, y_train, feature_name: str, out_dir: Path, numeric_features: List[str]
):
    """Plot partial dependence for a single numeric feature (one plot per class)."""
    feature_names = get_feature_names_from_pipeline(model)

    # Check if feature exists in the original feature set
    if feature_name not in numeric_features:
        print(f"Feature {feature_name} not in numeric_features. Skipping partial dependence plot.")
        return

    # Find feature index in the transformed feature space
    try:
        pre: ColumnTransformer = model.named_steps["preprocess"]
        transformed_idx = None
        current_idx = 0

        for name, transformer, cols in pre.transformers_:
            if name == "num":
                if feature_name in cols:
                    local_idx = cols.index(feature_name)
                    transformed_idx = current_idx + local_idx
                    break
                current_idx += len(cols)
            elif name == "cat":
                cat_encoder: OneHotEncoder = transformer.named_steps["onehot"]
                current_idx += len(cat_encoder.get_feature_names_out())
            elif name == "bin":
                current_idx += len(cols)

        if transformed_idx is None:
            print(f"Could not find {feature_name} in transformed feature space. Skipping.")
            return

    except (ValueError, AttributeError) as e:
        print(f"Error finding feature index for {feature_name}: {e}. Skipping.")
        return

    # Use a sample for faster computation (partial dependence can be slow)
    sample_size = min(500, len(X_train))
    X_sample = X_train.iloc[:sample_size].copy()

    try:
        # For binary classification (reburn prediction), show partial dependence for class 1 (Reburn)
        # Create a single plot showing how the feature affects reburn probability
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Use feature name directly - sklearn should handle it with pipelines
        try:
            display = PartialDependenceDisplay.from_estimator(
                model,
                X_sample,
                features=[feature_name],
                ax=ax,
                n_jobs=-1,
                kind="average",
            )
        except (ValueError, TypeError):
            # Fallback: use index if name doesn't work
            display = PartialDependenceDisplay.from_estimator(
                model,
                X_sample,
                features=[transformed_idx],
                ax=ax,
                n_jobs=-1,
                kind="average",
            )
        
        ax.set_title(f"Partial Dependence: {feature_name} → Reburn Probability", fontsize=12, fontweight="bold")
        ax.set_ylabel("Reburn Probability", fontsize=11)
        ax.set_xlabel(feature_name, fontsize=12)
        ax.grid(alpha=0.3, linestyle="--")

        plt.suptitle(f"Partial Dependence Analysis: {feature_name}", fontsize=14, fontweight="bold", y=0.995)
        plt.tight_layout()
        out_path = out_dir / f"partial_dependence_{feature_name.replace(' ', '_').replace('/', '_')}.png"
        plt.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close()
        print(f"Saved partial dependence plot to {out_path}")
    except Exception as e:
        print(f"Error generating partial dependence for {feature_name}: {e}")
        import traceback
        traceback.print_exc()


def plot_feature_correlation(df: pd.DataFrame, numeric_features: List[str], out_dir: Path):
    """Plot correlation heatmap of numeric features."""
    # Filter to only features that exist and have data
    available_features = [f for f in numeric_features if f in df.columns and not df[f].isna().all()]

    if len(available_features) < 2:
        print("Not enough numeric features for correlation plot. Skipping.")
        return

    corr_data = df[available_features].corr()

    plt.figure(figsize=(10, 8))
    mask = np.triu(np.ones_like(corr_data, dtype=bool))  # Mask upper triangle
    sns.heatmap(
        corr_data,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        square=True,
        linewidths=1,
        cbar_kws={"shrink": 0.8},
        mask=mask,  # Show only lower triangle
        vmin=-1,
        vmax=1,
    )
    plt.title("Feature Correlation Matrix (Lower Triangle)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    out_path = out_dir / "feature_correlation.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved feature correlation plot to {out_path}")


def plot_confusion_matrix_comparison(y_train, y_val, y_test, y_pred_train, y_pred_val, y_pred_test, out_dir: Path):
    """Create a side-by-side comparison of confusion matrices for reburn prediction."""
    from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    display_labels = ["No Reburn", "Reburn"]

    for ax, y_true, y_pred, title in zip(
        axes, [y_train, y_val, y_test], [y_pred_train, y_pred_val, y_pred_test], ["Train", "Validation", "Test"]
    ):
        labels = [0, 1]
        cm = confusion_matrix(y_true, y_pred, labels=labels, normalize="true")
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=display_labels)
        disp.plot(ax=ax, cmap="Blues", values_format=".2f")
        ax.set_title(f"{title} Set", fontsize=12, fontweight="bold")

    plt.suptitle("Reburn Risk Confusion Matrix Comparison Across Splits", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out_path = out_dir / "confusion_matrix_comparison.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved confusion matrix comparison to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate additional analysis plots for Random Forest model.")
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent
    
    parser.add_argument(
        "--data",
        type=Path,
        default=project_root / "data" / "fires_master.json",
        help="Path to master dataset JSON file",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=script_dir / "rf_model.joblib",
        help="Path to trained model joblib file",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=script_dir,  # Output to reburn/ directory
        help="Directory to save analysis plots",
    )
    args = parser.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading model and data...")
    # Load model
    model = joblib.load(args.model)
    print(f"Loaded model from {args.model}")

    # Load and prepare data (same as training script)
    df = load_data(args.data)
    df = prepare_features(df)  # Using raw features directly

    target = "reburn"
    group_col = "fire_id"

    # Recreate the same splits (same random_state=42)
    train_idx, val_idx, test_idx = split_groups(df, group_col=group_col, random_state=42)

    X = df.drop(columns=[target])
    y = df[target]

    # Get feature sets
    numeric_features, categorical_features, binary_features = select_feature_sets(df)

    print(f"\nDataset sizes: Train={len(train_idx)}, Val={len(val_idx)}, Test={len(test_idx)}")
    print(f"Numeric features: {numeric_features}")
    print(f"Categorical features: {categorical_features}")
    print(f"Binary features: {binary_features}\n")

    # Generate predictions
    print("Generating predictions...")
    y_pred_train = model.predict(X.iloc[train_idx])
    y_pred_val = model.predict(X.iloc[val_idx])
    y_pred_test = model.predict(X.iloc[test_idx])

    # Generate all plots
    print("\nGenerating analysis plots...\n")

    # 1. Per-class metrics (for test set)
    plot_per_class_metrics(y.iloc[test_idx], y_pred_test, out_dir, split_name="Test")

    # 2. Class distribution
    plot_class_distribution(y.iloc[train_idx], y.iloc[val_idx], y.iloc[test_idx], out_dir)

    # 3. Partial dependence plots for key features
    print("\nGenerating partial dependence plots (this may take a moment)...")
    # Focus on top features: land_burned_frequency is most important, but also show environmental factors
    key_features = ["land_burned_frequency", "elevation_m", "ph_val", "gw_depth_ft", "avg_temp_c"]
    for feat in key_features:
        if feat in numeric_features:
            plot_partial_dependence(model, X.iloc[train_idx], y.iloc[train_idx], feat, out_dir, numeric_features)

    # 4. Feature correlation
    plot_feature_correlation(df, numeric_features, out_dir)

    # 5. Confusion matrix comparison
    plot_confusion_matrix_comparison(
        y.iloc[train_idx],
        y.iloc[val_idx],
        y.iloc[test_idx],
        y_pred_train,
        y_pred_val,
        y_pred_test,
        out_dir,
    )

    print("\n✅ All analysis plots generated successfully!")
    print(f"📁 Output directory: {out_dir}")


if __name__ == "__main__":
    main()

