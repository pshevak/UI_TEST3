#!/usr/bin/env python3
"""
Improved U-Net Training Script for MTBS Burn Severity Segmentation
Addresses all user feedback:
1. 100 epochs training
2. Dice coefficient as F1 score
3. Better regularization for smoky validation curves
4. Improved visualizations with proper color scheme and legend placement
5. Output directory: /home/asures13/mtbs/results
6. Visualizations for train/val every 10 epochs + test set
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
import rasterio
from pathlib import Path
from tqdm import tqdm
from sklearn.metrics import accuracy_score, confusion_matrix
from scipy.ndimage import zoom

# Burn severity color mapping (6 classes)
BURN_SEVERITY_COLORS = {
    0: [34, 139, 34],      # Forest Green - Unburned to Low
    1: [173, 216, 230],    # Light Blue - Low  
    2: [255, 255, 0],      # Yellow - Moderate
    3: [255, 0, 0],        # Red - High
    4: [144, 238, 144],    # Light Green - Increased Greenness
    5: [211, 211, 211]     # Light Gray - Non-Processing Area Mask
}

def get_burn_severity_colormap():
    """Create colormap for burn severity visualization"""
    colors = np.array([BURN_SEVERITY_COLORS[i] for i in range(6)]) / 255.0
    return colors

class MTBSDataset(Dataset):
    """Dataset for MTBS burn severity data with improved preprocessing"""
    
    def __init__(self, csv_file, data_dir, normalize=True, augment=False):
        self.data = pd.read_csv(csv_file)
        self.data_dir = Path(data_dir)
        self.normalize = normalize
        self.augment = augment
        
        print(f"Loaded {len(self.data)} samples from {csv_file}")
        
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        row = self.data.iloc[idx]
        
        # Load post-fire image
        postfire_path = self.data_dir / 'postfire_images' / row['post_fire_file']
        with rasterio.open(postfire_path) as src:
            image = src.read().transpose(1, 2, 0)  # (H, W, C)
        
        # Load burn severity mask
        mask_path = self.data_dir / 'burn_severity' / row['burn_severity_file']
        with rasterio.open(mask_path) as src:
            mask = src.read(1)  # Single band
        
        # Handle different band counts (L5/L7: 7 bands, L8/L9: 11 bands)
        if image.shape[2] > 6:
            # Use first 6 bands (Blue, Green, Red, NIR, SWIR1, SWIR2)
            image = image[:, :, :6]
        
        # Resize to standard size (256x256)
        target_size = 256
        if image.shape[0] != target_size or image.shape[1] != target_size:
            # Resize image using scipy zoom for multi-channel
            zoom_h = target_size / image.shape[0]
            zoom_w = target_size / image.shape[1]
            
            # Resize image (handle multi-channel properly)
            image = zoom(image, (zoom_h, zoom_w, 1), order=1)  # Bilinear
            
            # Resize mask
            mask = zoom(mask, (zoom_h, zoom_w), order=0)  # Nearest neighbor
        
        # Normalize image
        if self.normalize:
            image = image.astype(np.float32) / 255.0
        
        # Ensure mask values are in valid range [0, 5]
        mask = np.clip(mask, 0, 5).astype(np.int64)
        
        # Convert to torch tensors
        image = torch.from_numpy(image).permute(2, 0, 1).float()  # (C, H, W)
        mask = torch.from_numpy(mask).long()
        
        # Data augmentation (if enabled)
        if self.augment:
            # Random horizontal flip
            if torch.rand(1) > 0.5:
                image = torch.flip(image, [2])
                mask = torch.flip(mask, [1])
            
            # Random vertical flip
            if torch.rand(1) > 0.5:
                image = torch.flip(image, [1])
                mask = torch.flip(mask, [0])
        
        return image, mask, row['fire_id']

class UNet(nn.Module):
    """U-Net with improved regularization"""
    
    def __init__(self, in_channels=6, num_classes=6, dropout_rate=0.2):
        super(UNet, self).__init__()
        
        # Encoder
        self.enc1 = self.conv_block(in_channels, 64, dropout_rate)
        self.enc2 = self.conv_block(64, 128, dropout_rate)
        self.enc3 = self.conv_block(128, 256, dropout_rate)
        self.enc4 = self.conv_block(256, 512, dropout_rate)
        
        # Bottleneck
        self.bottleneck = self.conv_block(512, 1024, dropout_rate)
        
        # Decoder
        self.upconv4 = nn.ConvTranspose2d(1024, 512, 2, stride=2)
        self.dec4 = self.conv_block(1024, 512, dropout_rate)
        
        self.upconv3 = nn.ConvTranspose2d(512, 256, 2, stride=2)
        self.dec3 = self.conv_block(512, 256, dropout_rate)
        
        self.upconv2 = nn.ConvTranspose2d(256, 128, 2, stride=2)
        self.dec2 = self.conv_block(256, 128, dropout_rate)
        
        self.upconv1 = nn.ConvTranspose2d(128, 64, 2, stride=2)
        self.dec1 = self.conv_block(128, 64, dropout_rate)
        
        # Final classifier
        self.final = nn.Conv2d(64, num_classes, 1)
        
    def conv_block(self, in_channels, out_channels, dropout_rate):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout_rate),
            nn.Conv2d(out_channels, out_channels, 3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout_rate)
        )
    
    def forward(self, x):
        # Encoder
        enc1 = self.enc1(x)
        enc2 = self.enc2(F.max_pool2d(enc1, 2))
        enc3 = self.enc3(F.max_pool2d(enc2, 2))
        enc4 = self.enc4(F.max_pool2d(enc3, 2))
        
        # Bottleneck
        bottleneck = self.bottleneck(F.max_pool2d(enc4, 2))
        
        # Decoder
        up4 = self.upconv4(bottleneck)
        up4 = torch.cat([up4, enc4], dim=1)
        dec4 = self.dec4(up4)
        
        up3 = self.upconv3(dec4)
        up3 = torch.cat([up3, enc3], dim=1)
        dec3 = self.dec3(up3)
        
        up2 = self.upconv2(dec3)
        up2 = torch.cat([up2, enc2], dim=1)
        dec2 = self.dec2(up2)
        
        up1 = self.upconv1(dec2)
        up1 = torch.cat([up1, enc1], dim=1)
        dec1 = self.dec1(up1)
        
        return self.final(dec1)

class DiceLoss(nn.Module):
    """Dice Loss for segmentation"""
    
    def __init__(self, smooth=1e-6):
        super(DiceLoss, self).__init__()
        self.smooth = smooth
    
    def forward(self, predictions, targets):
        # Apply softmax to predictions
        predictions = F.softmax(predictions, dim=1)
        
        # One-hot encode targets
        targets_one_hot = F.one_hot(targets, num_classes=6).permute(0, 3, 1, 2).float()
        
        # Calculate Dice coefficient for each class
        dice_scores = []
        for c in range(6):
            pred_c = predictions[:, c, :, :]
            target_c = targets_one_hot[:, c, :, :]
            
            intersection = (pred_c * target_c).sum()
            union = pred_c.sum() + target_c.sum()
            
            dice = (2. * intersection + self.smooth) / (union + self.smooth)
            dice_scores.append(dice)
        
        # Return 1 - mean dice (loss)
        return 1 - torch.stack(dice_scores).mean()

def dice_coefficient(predictions, targets, num_classes=6):
    """Calculate Dice coefficient (F1 score) for each class"""
    predictions = F.softmax(predictions, dim=1)
    pred_classes = torch.argmax(predictions, dim=1)
    
    dice_scores = []
    for c in range(num_classes):
        pred_c = (pred_classes == c).float()
        target_c = (targets == c).float()
        
        intersection = (pred_c * target_c).sum()
        union = pred_c.sum() + target_c.sum()
        
        if union == 0:
            dice = torch.tensor(1.0 if intersection == 0 else 0.0, device=predictions.device)
        else:
            dice = (2. * intersection) / union
        
        dice_scores.append(dice.item())
    
    return dice_scores

def calculate_iou(predictions, targets, num_classes=6):
    """Calculate IoU for each class"""
    predictions = F.softmax(predictions, dim=1)
    pred_classes = torch.argmax(predictions, dim=1)
    
    iou_scores = []
    for c in range(num_classes):
        pred_c = (pred_classes == c)
        target_c = (targets == c)
        
        intersection = (pred_c & target_c).sum().float()
        union = (pred_c | target_c).sum().float()
        
        if union == 0:
            iou = torch.tensor(1.0 if intersection == 0 else 0.0, device=predictions.device)
        else:
            iou = intersection / union
        
        iou_scores.append(iou.item())
    
    return iou_scores

class MTBSTrainer:
    """Improved trainer with all requested features"""
    
    def __init__(self, data_dir, splits_dir, output_dir='/home/asures13/mtbs/results', device='cuda'):
        self.data_dir = Path(data_dir)
        self.splits_dir = Path(splits_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.device = device
        
        # Create subdirectories
        (self.output_dir / 'checkpoints').mkdir(exist_ok=True)
        (self.output_dir / 'plots').mkdir(exist_ok=True)
        (self.output_dir / 'results').mkdir(exist_ok=True)
        (self.output_dir / 'visualizations').mkdir(exist_ok=True)
        
        # Initialize model with dropout for regularization
        self.model = UNet(in_channels=6, num_classes=6, dropout_rate=0.3).to(device)
        
        # Load datasets
        self._load_datasets()
        
        print(f"Trainer initialized with device: {device}")
        print(f"Output directory: {output_dir}")
    
    def _load_datasets(self):
        """Load train, validation, and test datasets"""
        # Load datasets with augmentation for training
        self.train_dataset = MTBSDataset(
            self.splits_dir / 'train.csv', 
            self.data_dir, 
            normalize=True, 
            augment=True
        )
        
        self.val_dataset = MTBSDataset(
            self.splits_dir / 'val.csv', 
            self.data_dir, 
            normalize=True, 
            augment=False
        )
        
        self.test_dataset = MTBSDataset(
            self.splits_dir / 'test.csv', 
            self.data_dir, 
            normalize=True, 
            augment=False
        )
        
        # Create data loaders
        self.train_loader = DataLoader(
            self.train_dataset, 
            batch_size=8, 
            shuffle=True, 
            num_workers=4,
            pin_memory=True
        )
        
        self.val_loader = DataLoader(
            self.val_dataset, 
            batch_size=8, 
            shuffle=False, 
            num_workers=4,
            pin_memory=True
        )
        
        self.test_loader = DataLoader(
            self.test_dataset, 
            batch_size=8, 
            shuffle=False, 
            num_workers=4,
            pin_memory=True
        )
        
        print(f"Data loaders created:")
        print(f"  Train: {len(self.train_dataset)} samples, {len(self.train_loader)} batches")
        print(f"  Val: {len(self.val_dataset)} samples, {len(self.val_loader)} batches")
        print(f"  Test: {len(self.test_dataset)} samples, {len(self.test_loader)} batches")
    
    def train_epoch(self, optimizer, criterion):
        """Train for one epoch"""
        self.model.train()
        total_loss = 0
        all_predictions = []
        all_targets = []
        
        for batch_idx, (images, masks, _) in enumerate(tqdm(self.train_loader, desc="Training")):
            images, masks = images.to(self.device), masks.to(self.device)
            
            optimizer.zero_grad()
            outputs = self.model(images)
            loss = criterion(outputs, masks)
            loss.backward()
            
            # Gradient clipping for stability
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            
            optimizer.step()
            
            total_loss += loss.item()
            
            # Store predictions and targets for metrics
            with torch.no_grad():
                pred_classes = torch.argmax(F.softmax(outputs, dim=1), dim=1)
                all_predictions.extend(pred_classes.cpu().numpy().flatten())
                all_targets.extend(masks.cpu().numpy().flatten())
        
        # Calculate metrics
        avg_loss = total_loss / len(self.train_loader)
        accuracy = accuracy_score(all_targets, all_predictions)
        
        # Calculate per-batch metrics for efficiency
        iou_scores = []
        dice_scores = []
        
        for batch_idx, (images, masks, _) in enumerate(self.train_loader):
            if batch_idx >= 10:  # Sample first 10 batches for speed
                break
            images, masks = images.to(self.device), masks.to(self.device)
            with torch.no_grad():
                outputs = self.model(images)
                batch_iou = calculate_iou(outputs, masks)
                batch_dice = dice_coefficient(outputs, masks)
                iou_scores.extend(batch_iou)
                dice_scores.extend(batch_dice)
        
        mean_iou = np.mean(iou_scores) if iou_scores else 0
        mean_dice = np.mean(dice_scores) if dice_scores else 0
        
        return avg_loss, {'accuracy': accuracy, 'mean_iou': mean_iou, 'mean_dice': mean_dice}
    
    def validate_epoch(self, criterion):
        """Validate for one epoch"""
        self.model.eval()
        total_loss = 0
        all_predictions = []
        all_targets = []
        
        with torch.no_grad():
            for images, masks, _ in tqdm(self.val_loader, desc="Validation"):
                images, masks = images.to(self.device), masks.to(self.device)
                
                outputs = self.model(images)
                loss = criterion(outputs, masks)
                total_loss += loss.item()
                
                pred_classes = torch.argmax(F.softmax(outputs, dim=1), dim=1)
                all_predictions.extend(pred_classes.cpu().numpy().flatten())
                all_targets.extend(masks.cpu().numpy().flatten())
        
        # Calculate metrics
        avg_loss = total_loss / len(self.val_loader)
        accuracy = accuracy_score(all_targets, all_predictions)
        
        # Calculate IoU and Dice for validation set
        iou_scores = []
        dice_scores = []
        
        with torch.no_grad():
            for images, masks, _ in self.val_loader:
                images, masks = images.to(self.device), masks.to(self.device)
                outputs = self.model(images)
                batch_iou = calculate_iou(outputs, masks)
                batch_dice = dice_coefficient(outputs, masks)
                iou_scores.extend(batch_iou)
                dice_scores.extend(batch_dice)
        
        mean_iou = np.mean(iou_scores) if iou_scores else 0
        mean_dice = np.mean(dice_scores) if dice_scores else 0
        
        return avg_loss, {'accuracy': accuracy, 'mean_iou': mean_iou, 'mean_dice': mean_dice}
    
    def visualize_predictions(self, epoch, dataset_name, num_samples=4):
        """Create improved visualizations with proper color scheme and legend"""
        self.model.eval()
        
        # Choose dataset
        if dataset_name == 'train':
            dataset = self.train_dataset
        elif dataset_name == 'val':
            dataset = self.val_dataset
        else:  # test
            dataset = self.test_dataset
        
        # Get colormap
        colors = get_burn_severity_colormap()
        
        fig, axes = plt.subplots(num_samples, 3, figsize=(15, 5*num_samples))
        if num_samples == 1:
            axes = axes.reshape(1, -1)
        
        with torch.no_grad():
            for i in range(num_samples):
                # Get sample
                image, mask, fire_id = dataset[i * (len(dataset) // num_samples)]
                image = image.unsqueeze(0).to(self.device)
                
                # Get prediction
                output = self.model(image)
                pred_mask = torch.argmax(F.softmax(output, dim=1), dim=1).cpu().numpy()[0]
                
                # Convert image for visualization (use RGB bands)
                img_vis = image[0, [2, 1, 0], :, :].cpu().numpy().transpose(1, 2, 0)  # RGB
                img_vis = np.clip(img_vis, 0, 1)
                
                # Create colored masks
                true_mask_colored = colors[mask.numpy()]
                pred_mask_colored = colors[pred_mask]
                
                # Plot
                axes[i, 0].imshow(img_vis)
                axes[i, 0].set_title(f'Input Image\n{fire_id}', fontsize=12)
                axes[i, 0].axis('off')
                
                axes[i, 1].imshow(true_mask_colored)
                axes[i, 1].set_title('Ground Truth', fontsize=12)
                axes[i, 1].axis('off')
                
                axes[i, 2].imshow(pred_mask_colored)
                axes[i, 2].set_title(f'Prediction (Epoch {epoch})', fontsize=12)
                axes[i, 2].axis('off')
        
        # Add legend in a good position (top right)
        legend_elements = []
        class_names = ['Unburned to Low', 'Low', 'Moderate', 'High', 'Increased Greenness', 'Non-Processing Area']
        
        for i, (class_name, color) in enumerate(zip(class_names, colors)):
            legend_elements.append(plt.Rectangle((0, 0), 1, 1, facecolor=color, label=class_name))
        
        # Place legend outside the plot area
        fig.legend(handles=legend_elements, loc='center right', bbox_to_anchor=(1.15, 0.5), fontsize=10)
        
        plt.tight_layout()
        plt.subplots_adjust(right=0.85)  # Make room for legend
        
        # Save
        save_path = self.output_dir / 'visualizations' / f'{dataset_name}_predictions_epoch_{epoch:03d}.png'
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"Saved {dataset_name} visualizations for epoch {epoch}")
    
    def train(self, num_epochs=100, lr=1e-4, weight_decay=1e-4):
        """Main training loop with improved hyperparameters"""
        
        # Combined loss: Dice + CrossEntropy for better class balance
        dice_loss = DiceLoss()
        ce_loss = nn.CrossEntropyLoss()
        
        def combined_criterion(outputs, targets):
            return 0.7 * dice_loss(outputs, targets) + 0.3 * ce_loss(outputs, targets)
        
        # Optimizer with weight decay for regularization
        optimizer = optim.AdamW(self.model.parameters(), lr=lr, weight_decay=weight_decay)
        
        # Learning rate scheduler
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=10, verbose=True
        )
        
        # Training history
        history = {
            'train_loss': [], 'val_loss': [],
            'train_acc': [], 'val_acc': [],
            'train_iou': [], 'val_iou': [],
            'train_dice': [], 'val_dice': []
        }
        
        best_val_iou = 0
        patience_counter = 0
        early_stopping_patience = 20
        
        print(f"Starting training for {num_epochs} epochs...")
        print("=" * 60)
        
        for epoch in range(1, num_epochs + 1):
            print(f"\nEpoch {epoch}/{num_epochs}")
            print("-" * 50)
            
            # Train
            train_loss, train_metrics = self.train_epoch(optimizer, combined_criterion)
            
            # Validate
            val_loss, val_metrics = self.validate_epoch(combined_criterion)
            
            # Update learning rate
            scheduler.step(val_loss)
            
            # Store history
            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
            history['train_acc'].append(train_metrics['accuracy'])
            history['val_acc'].append(val_metrics['accuracy'])
            history['train_iou'].append(train_metrics['mean_iou'])
            history['val_iou'].append(val_metrics['mean_iou'])
            history['train_dice'].append(train_metrics['mean_dice'])
            history['val_dice'].append(val_metrics['mean_dice'])
            
            # Print metrics
            print(f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
            print(f"Train Acc: {train_metrics['accuracy']:.4f}, Val Acc: {val_metrics['accuracy']:.4f}")
            print(f"Train IoU: {train_metrics['mean_iou']:.4f}, Val IoU: {val_metrics['mean_iou']:.4f}")
            print(f"Train Dice: {train_metrics['mean_dice']:.4f}, Val Dice: {val_metrics['mean_dice']:.4f}")
            
            # Save best model
            if val_metrics['mean_iou'] > best_val_iou:
                best_val_iou = val_metrics['mean_iou']
                torch.save(self.model.state_dict(), self.output_dir / 'checkpoints' / 'best_model.pth')
                patience_counter = 0
                print(f"New best model saved! Val IoU: {best_val_iou:.4f}")
            else:
                patience_counter += 1
            
            # Save checkpoint every 10 epochs
            if epoch % 10 == 0:
                torch.save(self.model.state_dict(), 
                          self.output_dir / 'checkpoints' / f'checkpoint_epoch_{epoch}.pth')
                
                # Create visualizations every 10 epochs
                self.visualize_predictions(epoch, 'train')
                self.visualize_predictions(epoch, 'val')
            
            # Early stopping
            if patience_counter >= early_stopping_patience:
                print(f"Early stopping triggered after {epoch} epochs")
                break
        
        # Final test set visualization
        self.visualize_predictions(epoch, 'test')
        
        # Save training history
        with open(self.output_dir / 'results' / 'training_history.json', 'w') as f:
            json.dump(history, f, indent=2)
        
        # Plot training curves
        self.plot_training_curves(history)
        
        return history
    
    def plot_training_curves(self, history):
        """Plot improved training curves"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        epochs = range(1, len(history['train_loss']) + 1)
        
        # Loss
        axes[0, 0].plot(epochs, history['train_loss'], 'b-', label='Train Loss', linewidth=2)
        axes[0, 0].plot(epochs, history['val_loss'], 'r-', label='Val Loss', linewidth=2)
        axes[0, 0].set_title('Training and Validation Loss', fontsize=14)
        axes[0, 0].set_xlabel('Epoch')
        axes[0, 0].set_ylabel('Loss')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        
        # Accuracy
        axes[0, 1].plot(epochs, history['train_acc'], 'b-', label='Train Accuracy', linewidth=2)
        axes[0, 1].plot(epochs, history['val_acc'], 'r-', label='Val Accuracy', linewidth=2)
        axes[0, 1].set_title('Training and Validation Accuracy', fontsize=14)
        axes[0, 1].set_xlabel('Epoch')
        axes[0, 1].set_ylabel('Accuracy')
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)
        
        # IoU
        axes[1, 0].plot(epochs, history['train_iou'], 'b-', label='Train IoU', linewidth=2)
        axes[1, 0].plot(epochs, history['val_iou'], 'r-', label='Val IoU', linewidth=2)
        axes[1, 0].set_title('Training and Validation IoU', fontsize=14)
        axes[1, 0].set_xlabel('Epoch')
        axes[1, 0].set_ylabel('Mean IoU')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)
        
        # Dice Coefficient (F1)
        axes[1, 1].plot(epochs, history['train_dice'], 'b-', label='Train Dice (F1)', linewidth=2)
        axes[1, 1].plot(epochs, history['val_dice'], 'r-', label='Val Dice (F1)', linewidth=2)
        axes[1, 1].set_title('Training and Validation Dice Coefficient (F1)', fontsize=14)
        axes[1, 1].set_xlabel('Epoch')
        axes[1, 1].set_ylabel('Dice Coefficient')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plots' / 'training_curves.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print("Training curves saved!")
    
    def evaluate_test_set(self):
        """Comprehensive evaluation on test set"""
        print("\n" + "=" * 60)
        print("EVALUATING ON TEST SET")
        print("=" * 60)
        
        # Load best model
        self.model.load_state_dict(torch.load(self.output_dir / 'checkpoints' / 'best_model.pth'))
        self.model.eval()
        
        all_predictions = []
        all_targets = []
        all_iou_scores = []
        all_dice_scores = []
        
        with torch.no_grad():
            for images, masks, _ in tqdm(self.test_loader, desc="Testing"):
                images, masks = images.to(self.device), masks.to(self.device)
                
                outputs = self.model(images)
                pred_classes = torch.argmax(F.softmax(outputs, dim=1), dim=1)
                
                all_predictions.extend(pred_classes.cpu().numpy().flatten())
                all_targets.extend(masks.cpu().numpy().flatten())
                
                # Calculate per-batch metrics
                batch_iou = calculate_iou(outputs, masks)
                batch_dice = dice_coefficient(outputs, masks)
                all_iou_scores.extend(batch_iou)
                all_dice_scores.extend(batch_dice)
        
        # Calculate overall metrics
        test_accuracy = accuracy_score(all_targets, all_predictions)
        
        # Per-class metrics
        per_class_iou = []
        per_class_dice = []
        per_class_precision = []
        per_class_recall = []
        
        for c in range(6):
            class_mask = np.array(all_targets) == c
            if class_mask.sum() > 0:
                class_predictions = np.array(all_predictions)[class_mask]
                class_targets = np.array(all_targets)[class_mask]
                
                # IoU and Dice
                class_iou_scores = [all_iou_scores[i] for i in range(len(all_iou_scores)) if i % 6 == c]
                class_dice_scores = [all_dice_scores[i] for i in range(len(all_dice_scores)) if i % 6 == c]
                
                per_class_iou.append(np.mean(class_iou_scores) if class_iou_scores else 0)
                per_class_dice.append(np.mean(class_dice_scores) if class_dice_scores else 0)
                
                # Precision and Recall
                tp = ((class_predictions == c) & (class_targets == c)).sum()
                fp = ((class_predictions == c) & (class_targets != c)).sum()
                fn = ((class_predictions != c) & (class_targets == c)).sum()
                
                precision = tp / (tp + fp) if (tp + fp) > 0 else 0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0
                
                per_class_precision.append(precision)
                per_class_recall.append(recall)
            else:
                per_class_iou.append(0)
                per_class_dice.append(0)
                per_class_precision.append(0)
                per_class_recall.append(0)
        
        # Results
        results = {
            'test_accuracy': test_accuracy,
            'test_mean_iou': np.mean(per_class_iou),
            'test_mean_dice': np.mean(per_class_dice),
            'per_class_iou': per_class_iou,
            'per_class_dice': per_class_dice,
            'per_class_precision': per_class_precision,
            'per_class_recall': per_class_recall
        }
        
        # Save results
        with open(self.output_dir / 'results' / 'test_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        # Print results
        class_names = ['Unburned to Low', 'Low', 'Moderate', 'High', 'Increased Greenness', 'Non-Processing Area']
        
        print(f"\nTest Accuracy: {test_accuracy:.4f}")
        print(f"Mean IoU: {results['test_mean_iou']:.4f}")
        print(f"Mean Dice (F1): {results['test_mean_dice']:.4f}")
        print("\nPer-class results:")
        print("-" * 80)
        print(f"{'Class':<20} {'IoU':<8} {'Dice':<8} {'Precision':<12} {'Recall':<8}")
        print("-" * 80)
        
        for i, class_name in enumerate(class_names):
            print(f"{class_name:<20} {per_class_iou[i]:<8.3f} {per_class_dice[i]:<8.3f} "
                  f"{per_class_precision[i]:<12.3f} {per_class_recall[i]:<8.3f}")
        
        return results

def main():
    """Main training function"""
    # Check device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    if device.type == 'cuda':
        print(f"GPU: {torch.cuda.get_device_name()}")
        print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    
    # Initialize trainer
    trainer = MTBSTrainer(
        data_dir='/scratch/asures13/mtbs/processed_data',
        splits_dir='/scratch/asures13/mtbs/processed_data/landsat_only/splits',
        output_dir='/home/asures13/mtbs/results',
        device=device
    )
    
    print("\n" + "=" * 60)
    print("STARTING IMPROVED MTBS BURN SEVERITY SEGMENTATION TRAINING")
    print("=" * 60)
    
    # Train model
    history = trainer.train(num_epochs=100, lr=1e-4, weight_decay=1e-4)
    
    # Evaluate on test set
    test_results = trainer.evaluate_test_set()
    
    print("\n" + "=" * 60)
    print("TRAINING COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print(f"Results saved to: {trainer.output_dir}")
    print(f"Best validation IoU: {max(history['val_iou']):.4f}")
    print(f"Final test IoU: {test_results['test_mean_iou']:.4f}")
    print(f"Final test Dice (F1): {test_results['test_mean_dice']:.4f}")

if __name__ == "__main__":
    main()