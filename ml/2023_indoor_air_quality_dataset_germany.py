# -*- coding: utf-8 -*-

# Fix MKL threading issue before importing any libraries
import os
os.environ['MKL_THREADING_LAYER'] = 'GNU'
os.environ['MKL_SERVICE_FORCE_INTEL'] = '1'

#Import required libraries
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to avoid display issues
import matplotlib.pyplot as plt
import seaborn as sns

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Create subdirectories for organized output
PLOTS_DIR = os.path.join(SCRIPT_DIR, 'plots')
os.makedirs(PLOTS_DIR, exist_ok=True)

#Read the datasets
lab = pd.read_csv(os.path.join(SCRIPT_DIR, 'laboratory.csv'))
room = pd.read_csv(os.path.join(SCRIPT_DIR, 'one_room_apartement.csv'))
#Convert timestamp to datetime format
lab['timestamp'] = pd.to_datetime(lab['timestamp'])
room['timestamp'] = pd.to_datetime(room['timestamp'])
#Sort values by time
lab = lab.sort_values(by='timestamp').reset_index()
room = room.sort_values(by='timestamp').reset_index()
#drop old index column
lab = lab.drop(columns='index', axis=1)
room = room.drop(columns='index', axis=1)
#Create a column by seconds from the beginning of the study
lab['Duration']= ((lab['timestamp']-lab['timestamp'].min()).dt.total_seconds())/3600
room['Duration']= ((room['timestamp']-room['timestamp'].min()).dt.total_seconds())/3600

#Check the number of data and columns
print("Lab info:")
lab.info()
print("\nRoom info:")
room.info()

#Check missing values
print("Lab missing values:")
print(lab.isna().sum())
print("\nRoom missing values:")
print(room.isna().sum())

lab_h = lab.groupby(lab['Duration'][::30]).mean()
room_h = room.groupby(room['Duration'][::30]).mean()

"""# **I do not need all above parameters in this study so I only select several parameters**"""

lab_n = lab_h[['temperature', 'humidity', 'co2', 'tvoc', 'o3', 'pm1', 'pm2_5', 'pm10']].reset_index()
room_n = room_h[['temperature', 'humidity', 'co2', 'tvoc', 'o3', 'pm1', 'pm2_5', 'pm10']].reset_index()
lab_n = lab_n.drop('Duration', axis=1)
room_n = room_n.drop('Duration', axis=1)
lab_n.insert(0, 'Time',lab_h['Duration'].round().to_list())
room_n.insert(0, 'Time',room_h['Duration'].round().to_list())

# Define constant for IAQ without O3 column name
IAQ_WITHOUT_O3 = 'IAQ_without o3'

room_n['IAQ'] = (room_n['pm1']<=10) & (room_n['pm2_5']<=25) & (room_n['pm10']<=50) & (room_n['co2']<800) & (room_n['tvoc']<300) & (room_n['o3']<18)
room_n['IAQ'] = room_n['IAQ'].astype(object).replace({False:'POOR', True:'GOOD'})

room_n[IAQ_WITHOUT_O3] = (room_n['pm1']<=10) & (room_n['pm2_5']<=25) & (room_n['pm10']<=50) & (room_n['co2']<800) & (room_n['tvoc']<300)
room_n[IAQ_WITHOUT_O3] = room_n[IAQ_WITHOUT_O3].astype(object).replace({False:'POOR', True:'GOOD'})

lab_n['IAQ'] = (lab_n['pm1']<=10) & (lab_n['pm2_5']<=25) & (lab_n['pm10']<=50) & (lab_n['co2']<800) & (lab_n['tvoc']<300) & (lab_n['o3']<18)
lab_n['IAQ'] = lab_n['IAQ'].astype(object).replace({False:'POOR', True:'GOOD'})

print("Lab_n DataFrame:")
print(lab_n)

fig, ax = plt.subplots(figsize=(4, 4))
lab_iaq_values = lab_n['IAQ'].to_numpy()
unique_vals, counts = np.unique(lab_iaq_values, return_counts=True)
ax.pie(counts/len(lab_n), labels=unique_vals.tolist(), autopct='%.1f%%')
ax.set_title('Lab IAQ_Overall')
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, 'lab_iaq_overall.png'), dpi=150, bbox_inches='tight')
print("Saved: plots/lab_iaq_overall.png")
plt.close()

print("Room_n DataFrame:")
print(room_n)

fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax1 = plt.subplot(1, 2, 1)
room_iaq_values = room_n['IAQ'].to_numpy()
unique_vals1, counts1 = np.unique(room_iaq_values, return_counts=True)
ax1.pie(counts1/len(room_n), labels=unique_vals1.tolist(), autopct='%.1f%%')
ax1.set_title('Room IAQ_Overall')
ax2 = plt.subplot(1, 2, 2)
room_iaq_no_o3_values = room_n[IAQ_WITHOUT_O3].to_numpy()
unique_vals2, counts2 = np.unique(room_iaq_no_o3_values, return_counts=True)
ax2.pie(counts2/len(room_n), labels=unique_vals2.tolist(), autopct='%.1f%%')
ax2.set_title('Room IAQ_without o3_Overall')
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, 'room_iaq_comparison.png'), dpi=150, bbox_inches='tight')
print("Saved: plots/room_iaq_comparison.png")
plt.close()

### Logistic Regression
# Lab
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
lab_X = lab_n[['co2', 'tvoc', 'pm1', 'pm2_5', 'pm10', 'o3']]
lib = {'GOOD': 1, 'POOR': 0}
lab_Y = lab_n['IAQ'].map(lib).values
lab_X_train, lab_X_test, lab_Y_train, lab_Y_test = train_test_split(lab_X, lab_Y, test_size= 0.3, random_state=101)
lab_LoR = LogisticRegression(max_iter = 10000, random_state=42).fit(lab_X_train, lab_Y_train)
lab_pred = lab_LoR.predict(lab_X_test)
from sklearn.metrics import accuracy_score
print('Accuracy = ', accuracy_score(lab_Y_test, lab_pred))

# Room
room_X = room_n[['co2', 'tvoc', 'pm1', 'pm2_5', 'pm10', 'o3']]
lib = {'GOOD': 1, 'POOR': 0}
room_Y = room_n['IAQ'].map(lib).values
room_X_train, room_X_test, room_Y_train, room_Y_test = train_test_split(room_X, room_Y, test_size= 0.3, random_state=101)
room_LoR = LogisticRegression(max_iter = 10000, random_state=42).fit(room_X_train, room_Y_train)
room_pred = room_LoR.predict(room_X_test)
print('Accuracy = ', accuracy_score(room_Y_test, room_pred))

"""### Thermal Comfort"""

# Install pythermalcomfort if not already installed
# Run: pip install pythermalcomfort

import pythermalcomfort
from pythermalcomfort import utilities

mean_list_lab = []
mean_list_room = []
chunk = 24
i=0
while i <= len(lab_n['temperature']):
    start = i
    end = i + 24
    c = lab_n['temperature'][start:end]
    mean = sum(c)/len(c)
    mean_list_lab.append(mean)
    i = end
i=0
while i <= len(room_n['temperature']):
    start = i
    end = i + 24
    c = room_n['temperature'][start:end]
    mean = sum(c)/len(c)
    mean_list_room.append(mean)
    i = end

t_running_mean_lab = utilities.running_mean_outdoor_temperature(mean_list_lab[::-1], alpha=0.8, units='SI')
t_running_mean_room = utilities.running_mean_outdoor_temperature(mean_list_room[::-1], alpha=0.8, units='SI')

from pythermalcomfort.models import adaptive_ashrae

v=0.1
adp_t_c_lab = adaptive_ashrae(lab_n['temperature'].tolist(), lab_n['temperature'].tolist(), t_running_mean_lab, v, units='SI', limit_inputs=True)
adp_t_c_room = adaptive_ashrae(room_n['temperature'].tolist(), room_n['temperature'].tolist(), t_running_mean_room, v, units='SI', limit_inputs=True)

lab_n['temperature'][adp_t_c_lab['acceptability_90']]

plt.figure(figsize=(10,5))
plt.plot(lab_n['Time'], adp_t_c_lab['tmp_cmf'], label = 'Comfort temperature')
plt.plot(lab_n['Time'], adp_t_c_lab['tmp_cmf_80_low'], label = '80-low')
plt.plot(lab_n['Time'], adp_t_c_lab['tmp_cmf_80_up'], label = '80-up')
plt.plot(lab_n['Time'], adp_t_c_lab['tmp_cmf_90_low'], label = '90-low')
plt.plot(lab_n['Time'], adp_t_c_lab['tmp_cmf_90_up'], label = '90-up')
plt.plot(lab_n['Time'], lab_n['temperature'], label= 'Indoor temperature')
plt.scatter(lab_n['Time'][adp_t_c_lab['acceptability_90']], lab_n['temperature'][adp_t_c_lab['acceptability_90']], label= '90% acceptable')
plt.legend(loc='center right', bbox_to_anchor=(1.28, 0.5))
plt.savefig(os.path.join(PLOTS_DIR, 'lab_thermal_comfort.png'), dpi=150, bbox_inches='tight')
print("Saved: plots/lab_thermal_comfort.png")
plt.close()

plt.figure(figsize=(10,5))
plt.plot(room_n['Time'], adp_t_c_room['tmp_cmf'], label = 'Comfort temperature')
plt.plot(room_n['Time'], adp_t_c_room['tmp_cmf_80_low'], label = '80-low')
plt.plot(room_n['Time'], adp_t_c_room['tmp_cmf_80_up'], label = '80-up')
plt.plot(room_n['Time'], adp_t_c_room['tmp_cmf_90_low'], label = '90-low')
plt.plot(room_n['Time'], adp_t_c_room['tmp_cmf_90_up'], label = '90-up')
plt.plot(room_n['Time'], room_n['temperature'], label= 'Indoor temperature')
plt.scatter(room_n['Time'][adp_t_c_room['acceptability_90']], room_n['temperature'][adp_t_c_room['acceptability_90']], label= '90% acceptable')
plt.legend(loc='center right', bbox_to_anchor=(1.28, 0.5))
plt.savefig(os.path.join(PLOTS_DIR, 'room_thermal_comfort.png'), dpi=150, bbox_inches='tight')
print("Saved: plots/room_thermal_comfort.png")
plt.close()

"""### Temperature Prediction for IoT Devices"""

print("\n" + "="*60)
print("STARTING TEMPERATURE PREDICTION SECTION")
print("="*60)

# Prepare temperature data for time series prediction
# Using room data as it has more variability
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
import warnings
warnings.filterwarnings('ignore')

# Use the original room dataframe with timestamps for better time series handling
room_temp = room[['timestamp', 'temperature']].copy()
room_temp = room_temp.set_index('timestamp')
room_temp = room_temp.resample('30min').mean()  # Resample to 30-minute intervals
room_temp = room_temp.dropna()

print(f"\nTemperature data shape: {room_temp.shape}")
print(f"Date range: {room_temp.index.min()} to {room_temp.index.max()}")
print(f"Temperature range: {room_temp['temperature'].min():.2f}°C to {room_temp['temperature'].max():.2f}°C")

# Scale the data
scaler = MinMaxScaler(feature_range=(0, 1))
temp_scaled = scaler.fit_transform(room_temp.values)

# Create sequences for LSTM (using past 24 hours to predict next hour)
def create_sequences(data, seq_length=48):  # 48 = 24 hours at 30-min intervals
    X, y = [], []
    for i in range(len(data) - seq_length):
        X.append(data[i:i+seq_length])
        y.append(data[i+seq_length])
    return np.array(X), np.array(y)

seq_length = 48  # Use 24 hours of history
X, y = create_sequences(temp_scaled, seq_length)

print(f"\nSequence shape: X={X.shape}, y={y.shape}")

# Split data: 80% train, 10% validation, 10% test
train_size = int(len(X) * 0.8)
val_size = int(len(X) * 0.1)

X_train, y_train = X[:train_size], y[:train_size]
X_val, y_val = X[train_size:train_size+val_size], y[train_size:train_size+val_size]
X_test, y_test = X[train_size+val_size:], y[train_size+val_size:]

print(f"Train: {X_train.shape}, Validation: {X_val.shape}, Test: {X_test.shape}")
# Initialize variables for both models
import time
import joblib
import os

lstm_available = False
lstm_model = None
history = None
rmse_lstm = mae_lstm = training_time_lstm = inference_time_lstm = model_size_lstm = 0
rmse_rf = mae_rf = training_time_rf = inference_time_rf = model_size_rf = 0
rmse_nb = mae_nb = training_time_nb = inference_time_nb = model_size_nb = 0
y_pred_lstm = y_pred_rf = y_pred_nb = None

print("\n" + "="*70)
print(" " * 18 + "TEMPERATURE PREDICTION TRAINING")
print("="*70)

# =============================================================================
# MODEL 1: LSTM (TensorFlow/Keras) - Optional
# =============================================================================
try:
    from tensorflow.keras.models import Sequential # pyright: ignore[reportMissingImports]
    from tensorflow.keras.layers import LSTM, Dense, Dropout # pyright: ignore[reportMissingImports]
    from tensorflow.keras.callbacks import EarlyStopping # pyright: ignore[reportMissingImports]

    print("\n[1/2] TRAINING LSTM MODEL (TensorFlow/Keras)")
    print("="*70)

    start_time = time.time()

    # Build lightweight LSTM model suitable for IoT
    lstm_model = Sequential([
        LSTM(32, activation='relu', return_sequences=True, input_shape=(seq_length, 1)),
        Dropout(0.2),
        LSTM(16, activation='relu'),
        Dropout(0.2),
        Dense(8, activation='relu'),
        Dense(1)
    ])

    lstm_model.compile(optimizer='adam', loss='mse', metrics=['mae'])

    print("\nLSTM Model Summary:")
    lstm_model.summary()

    # Train with early stopping
    early_stop = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)

    print("\n[INFO] Training LSTM model...")
    history = lstm_model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=50,
        batch_size=32,
        callbacks=[early_stop],
        verbose=1
    )

    training_time_lstm = time.time() - start_time

    # Predict on test set
    inference_start = time.time()
    y_pred_lstm_scaled = lstm_model.predict(X_test, verbose=0)
    inference_time_lstm = (time.time() - inference_start) / len(X_test) * 1000  # ms per prediction

    # Inverse transform predictions
    y_pred_lstm = scaler.inverse_transform(y_pred_lstm_scaled)
    y_test_actual = scaler.inverse_transform(y_test.reshape(-1, 1))

    # Calculate metrics
    mse_lstm = mean_squared_error(y_test_actual, y_pred_lstm)
    rmse_lstm = np.sqrt(mse_lstm)
    mae_lstm = mean_absolute_error(y_test_actual, y_pred_lstm)

    # Save model and get size
    lstm_model.save(os.path.join(SCRIPT_DIR, 'temperature_lstm_model.h5'))
    model_size_lstm = os.path.getsize(os.path.join(SCRIPT_DIR, 'temperature_lstm_model.h5')) / (1024 * 1024)

    print("\n[LSTM Training Complete]")
    print(f"   RMSE: {rmse_lstm:.4f}°C")
    print(f"   MAE: {mae_lstm:.4f}°C")
    print(f"   Training time: {training_time_lstm:.2f}s")
    print(f"   Inference time: {inference_time_lstm:.3f}ms per prediction")
    print(f"   Model size: {model_size_lstm:.2f}MB")
    print("   Model saved: temperature_lstm_model.h5")

    lstm_available = True

except ImportError as e:
    print(f"\n[WARNING] TensorFlow not available: {e}")
    print("   Skipping LSTM model training...")
except Exception as e:
    print(f"\n[ERROR] LSTM training failed: {e}")
    print("   Continuing with traditional ML models...")

# =============================================================================
# MODEL 2: Random Forest (scikit-learn) - ALWAYS TRAIN
# =============================================================================
from sklearn.ensemble import RandomForestRegressor

print("\n[2/3] TRAINING RANDOM FOREST MODEL (scikit-learn)")
print("="*70)

# Flatten sequences for traditional ML models
X_train_flat = X_train.reshape(X_train.shape[0], -1)
X_val_flat = X_val.reshape(X_val.shape[0], -1)
X_test_flat = X_test.reshape(X_test.shape[0], -1)

start_time = time.time()

print("\n[INFO] Training Random Forest model (IoT-optimized)...")

# Use smaller Random Forest for IoT deployment
rf_model = RandomForestRegressor(
    n_estimators=10,
    max_depth=10,
    min_samples_split=5,
    min_samples_leaf=2,
    max_features='sqrt',
    random_state=42,
    n_jobs=-1,
    verbose=1
)

rf_model.fit(X_train_flat, y_train.ravel())

training_time_rf = time.time() - start_time

# Predict on test set
inference_start = time.time()
y_pred_rf_scaled = rf_model.predict(X_test_flat)
inference_time_rf = (time.time() - inference_start) / len(X_test_flat) * 1000  # ms per prediction

# Inverse transform predictions
y_pred_rf = scaler.inverse_transform(y_pred_rf_scaled.reshape(-1, 1))

# Ensure y_test_actual is defined (in case LSTM wasn't trained)
if not lstm_available:
    y_test_actual = scaler.inverse_transform(y_test.reshape(-1, 1))

# Calculate metrics
mse_rf = mean_squared_error(y_test_actual, y_pred_rf)
rmse_rf = np.sqrt(mse_rf)
mae_rf = mean_absolute_error(y_test_actual, y_pred_rf)

# Save model and get size
joblib.dump(rf_model, os.path.join(SCRIPT_DIR, 'temperature_rf_model.joblib'))
joblib.dump(scaler, os.path.join(SCRIPT_DIR, 'temperature_scaler.joblib'))
model_size_rf = os.path.getsize(os.path.join(SCRIPT_DIR, 'temperature_rf_model.joblib')) / (1024 * 1024)

print("\n[Random Forest Training Complete]")
print(f"   RMSE: {rmse_rf:.4f}°C")
print(f"   MAE: {mae_rf:.4f}°C")
print(f"   Training time: {training_time_rf:.2f}s")
print(f"   Inference time: {inference_time_rf:.3f}ms per prediction")
print(f"   Model size: {model_size_rf:.2f}MB")
print("   Models saved: temperature_rf_model.joblib, temperature_scaler.joblib")

# =============================================================================
# MODEL 3: Gaussian Naive Bayes (scikit-learn) - ALWAYS TRAIN
# =============================================================================
from sklearn.naive_bayes import GaussianNB

print("\n[3/3] TRAINING NAIVE BAYES MODEL (scikit-learn)")
print("="*70)

start_time = time.time()

print("\n[INFO] Training Gaussian Naive Bayes model with REACTIVE improvements...")

# IMPROVEMENT 1: Extract temporal features from sequences for better reactivity
print("   [+] Extracting temporal features (trend, velocity, acceleration)...")
def extract_temporal_features(X_flat, seq_length=48):
    """
    Extract temporal features from flattened sequences to make NB more reactive.
    Features: mean, std, min, max, trend (linear slope), velocity (recent change rate),
    acceleration (change in velocity), recent_mean (last 25% of sequence)
    """
    X_reshaped = X_flat.reshape(X_flat.shape[0], seq_length)

    features = []
    features.append(np.mean(X_reshaped, axis=1))          # Overall mean
    features.append(np.std(X_reshaped, axis=1))           # Volatility
    features.append(np.min(X_reshaped, axis=1))           # Min temp
    features.append(np.max(X_reshaped, axis=1))           # Max temp

    # Trend (linear regression slope) - captures direction
    time_steps = np.arange(seq_length)
    trends = np.array([np.polyfit(time_steps, x, 1)[0] for x in X_reshaped])
    features.append(trends)

    # Velocity (rate of change in recent window) - reactivity to immediate changes
    recent_window = seq_length // 4  # Last 25% (6 hours)
    velocity = (X_reshaped[:, -1] - X_reshaped[:, -recent_window]) / recent_window
    features.append(velocity)

    # Acceleration (change in velocity) - detects pattern shifts
    mid_point = seq_length // 2
    velocity_recent = (X_reshaped[:, -1] - X_reshaped[:, mid_point]) / (seq_length - mid_point)
    velocity_past = (X_reshaped[:, mid_point] - X_reshaped[:, 0]) / mid_point
    acceleration = velocity_recent - velocity_past
    features.append(acceleration)

    # Recent mean (last 25% of sequence) - emphasizes recent behavior
    recent_mean = np.mean(X_reshaped[:, -recent_window:], axis=1)
    features.append(recent_mean)

    # Last value (most recent observation) - highest weight on current state
    features.append(X_reshaped[:, -1])

    return np.column_stack(features)

# Extract temporal features for all datasets
X_train_temporal = extract_temporal_features(X_train_flat, seq_length)
X_val_temporal = extract_temporal_features(X_val_flat, seq_length)
X_test_temporal = extract_temporal_features(X_test_flat, seq_length)

print(f"   [✓] Temporal features extracted: {X_train_temporal.shape[1]} features per sample")

# IMPROVEMENT 2: Adaptive binning based on data distribution (more bins in dense regions)
print("   [+] Using adaptive quantile-based binning for better granularity...")
n_bins = 100  # Increased from 50 for finer granularity (2x more reactive)

# Use quantile-based binning instead of uniform (adapts to data distribution)
bin_edges = np.percentile(y_train, np.linspace(0, 100, n_bins))
# Ensure unique bin edges
bin_edges = np.unique(bin_edges)
n_bins = len(bin_edges)

y_train_binned = np.digitize(y_train.ravel(), bins=bin_edges)
y_test_binned = np.digitize(y_test.ravel(), bins=bin_edges)

print(f"   [✓] Adaptive binning created: {n_bins} bins")

# IMPROVEMENT 3: Train Naive Bayes with temporal features
nb_model = GaussianNB()
nb_model.fit(X_train_temporal, y_train_binned)

training_time_nb = time.time() - start_time

# Predict on test set with temporal features
inference_start = time.time()
y_pred_nb_binned = nb_model.predict(X_test_temporal)
inference_time_nb = (time.time() - inference_start) / len(X_test_temporal) * 1000  # ms per prediction

# IMPROVEMENT 4: Use probability-weighted prediction instead of hard classification
# This makes predictions smoother and more reactive to uncertainty
print("   [+] Using probability-weighted prediction for smoother outputs...")
y_pred_proba = nb_model.predict_proba(X_test_temporal)

# Convert probabilities to continuous predictions (expectation over all bins)
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
if len(bin_centers) < y_pred_proba.shape[1]:
    # Handle edge case where bin_edges created fewer bins than classes
    bin_centers = np.pad(bin_centers, (0, y_pred_proba.shape[1] - len(bin_centers)),
                         mode='edge')

y_pred_nb_scaled = np.dot(y_pred_proba, bin_centers[:y_pred_proba.shape[1]])

# Inverse transform predictions
y_pred_nb = scaler.inverse_transform(y_pred_nb_scaled.reshape(-1, 1))

# Calculate metrics
mse_nb = mean_squared_error(y_test_actual, y_pred_nb)
rmse_nb = np.sqrt(mse_nb)
mae_nb = mean_absolute_error(y_test_actual, y_pred_nb)

# Save model, scaler, bin_edges, and temporal feature extractor function
joblib.dump(nb_model, os.path.join(SCRIPT_DIR, 'temperature_nb_model.joblib'))
joblib.dump(bin_edges, os.path.join(SCRIPT_DIR, 'temperature_nb_bins.joblib'))
# Save metadata for feature extraction
nb_metadata = {
    'seq_length': seq_length,
    'n_bins': n_bins,
    'features': ['mean', 'std', 'min', 'max', 'trend', 'velocity', 'acceleration', 'recent_mean', 'last_value']
}
joblib.dump(nb_metadata, os.path.join(SCRIPT_DIR, 'temperature_nb_metadata.joblib'))
model_size_nb = os.path.getsize(os.path.join(SCRIPT_DIR, 'temperature_nb_model.joblib')) / (1024 * 1024)

print("\n[Naive Bayes Training Complete - REACTIVE MODE]")
print(f"   RMSE: {rmse_nb:.4f}°C")
print(f"   MAE: {mae_nb:.4f}°C")
print(f"   Training time: {training_time_nb:.2f}s")
print(f"   Inference time: {inference_time_nb:.3f}ms per prediction")
print(f"   Model size: {model_size_nb:.2f}MB")
print("   Improvements applied:")
print("      ✓ Temporal feature engineering (9 features)")
print("      ✓ Adaptive quantile binning ({n_bins} bins)")
print("      ✓ Probability-weighted predictions")
print("   Models saved: temperature_nb_model.joblib, temperature_nb_bins.joblib, temperature_nb_metadata.joblib")

# =============================================================================
# VISUALIZATION: Plot predictions for all models
# =============================================================================
print("\n[INFO] Generating visualizations...")

if lstm_available and y_pred_lstm is not None and history is not None:
    # Plot all three models together
    plt.figure(figsize=(16, 12))

    # Plot 1: LSTM Training History
    plt.subplot(2, 3, 1)
    plt.plot(history.history['loss'], label='Training Loss')
    plt.plot(history.history['val_loss'], label='Validation Loss')
    plt.title('LSTM Training History')
    plt.xlabel('Epoch')
    plt.ylabel('Loss (MSE)')
    plt.legend()
    plt.grid(True)

    # Plot 2: All Models Predictions Comparison
    plt.subplot(2, 3, 2)
    plot_range = min(200, len(y_test_actual))
    plt.plot(y_test_actual[:plot_range], label='Actual', linewidth=2, color='black')
    plt.plot(y_pred_lstm[:plot_range], label='LSTM', linewidth=1.5, alpha=0.7, color='blue')
    plt.plot(y_pred_rf[:plot_range], label='Random Forest', linewidth=1.5, alpha=0.7, color='green')
    plt.plot(y_pred_nb[:plot_range], label='Naive Bayes', linewidth=1.5, alpha=0.7, color='orange')
    plt.title('All Models Comparison')
    plt.xlabel('Time Steps (30-min intervals)')
    plt.ylabel('Temperature (°C)')
    plt.legend()
    plt.grid(True)

    # Plot 3: RMSE Comparison Bar Chart
    plt.subplot(2, 3, 3)
    models = ['LSTM', 'Random Forest', 'Naive Bayes']
    rmses = [rmse_lstm, rmse_rf, rmse_nb]
    colors = ['blue', 'green', 'orange']
    bars = plt.bar(models, rmses, color=colors, alpha=0.7)
    plt.title('Model RMSE Comparison')
    plt.ylabel('RMSE (°C)')
    plt.grid(True, axis='y', alpha=0.3)
    for bar, rmse_val in zip(bars, rmses):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f'{rmse_val:.3f}', ha='center', va='bottom')

    # Plot 4: LSTM Error Distribution
    plt.subplot(2, 3, 4)
    errors_lstm = (y_test_actual - y_pred_lstm).flatten()
    plt.hist(errors_lstm, bins=50, edgecolor='black', alpha=0.7, color='blue')
    plt.title(f'LSTM Error (Mean: {errors_lstm.mean():.4f}°C)')
    plt.xlabel('Prediction Error (°C)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)

    # Plot 5: RF Error Distribution
    plt.subplot(2, 3, 5)
    errors_rf = (y_test_actual - y_pred_rf).flatten()
    plt.hist(errors_rf, bins=50, edgecolor='black', alpha=0.7, color='green')
    plt.title(f'RF Error (Mean: {errors_rf.mean():.4f}°C)')
    plt.xlabel('Prediction Error (°C)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)

    # Plot 6: NB Error Distribution
    plt.subplot(2, 3, 6)
    errors_nb = (y_test_actual - y_pred_nb).flatten()
    plt.hist(errors_nb, bins=50, edgecolor='black', alpha=0.7, color='orange')
    plt.title(f'NB Error (Mean: {errors_nb.mean():.4f}°C)')
    plt.xlabel('Prediction Error (°C)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'temperature_prediction_comparison.png'), dpi=150, bbox_inches='tight')
    print("Saved: plots/temperature_prediction_comparison.png")
    plt.close()

    # Use best model for forecasting
    best_rmse = min(rmse_lstm, rmse_rf, rmse_nb)
    if best_rmse == rmse_lstm:
        model_used = "LSTM"
        best_model = lstm_model
        rmse = rmse_lstm
        mae = mae_lstm
    elif best_rmse == rmse_rf:
        model_used = "Random Forest"
        best_model = rf_model
        rmse = rmse_rf
        mae = mae_rf
    else:
        model_used = "Naive Bayes"
        best_model = nb_model
        rmse = rmse_nb
        mae = mae_nb
else:
    # Plot only traditional ML models (RF and NB)
    plt.figure(figsize=(16, 10))

    # Plot 1: All Models Predictions vs Actual
    plt.subplot(2, 3, 1)
    plot_range = min(200, len(y_test_actual))
    plt.plot(y_test_actual[:plot_range], label='Actual Temperature', linewidth=2, color='black')
    plt.plot(y_pred_rf[:plot_range], label='Random Forest', linewidth=1.5, alpha=0.7, color='green')
    plt.plot(y_pred_nb[:plot_range], label='Naive Bayes', linewidth=1.5, alpha=0.7, color='orange')
    plt.title('Model Predictions Comparison')
    plt.xlabel('Time Steps (30-min intervals)')
    plt.ylabel('Temperature (°C)')
    plt.legend()
    plt.grid(True)

    # Plot 2: RMSE Comparison
    plt.subplot(2, 3, 2)
    models = ['Random Forest', 'Naive Bayes']
    rmses = [rmse_rf, rmse_nb]
    colors = ['green', 'orange']
    bars = plt.bar(models, rmses, color=colors, alpha=0.7)
    plt.title('Model RMSE Comparison')
    plt.ylabel('RMSE (°C)')
    plt.grid(True, axis='y', alpha=0.3)
    for bar, rmse_val in zip(bars, rmses):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f'{rmse_val:.3f}', ha='center', va='bottom')

    # Plot 3: MAE Comparison
    plt.subplot(2, 3, 3)
    maes = [mae_rf, mae_nb]
    bars = plt.bar(models, maes, color=colors, alpha=0.7)
    plt.title('Model MAE Comparison')
    plt.ylabel('MAE (°C)')
    plt.grid(True, axis='y', alpha=0.3)
    for bar, mae_val in zip(bars, maes):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f'{mae_val:.3f}', ha='center', va='bottom')

    # Plot 4: RF Predictions Detail
    plt.subplot(2, 3, 4)
    plt.plot(y_test_actual[:plot_range], label='Actual', linewidth=2, color='black')
    plt.plot(y_pred_rf[:plot_range], label='RF Predicted', linewidth=2, alpha=0.7, color='green')
    plt.title(f'Random Forest Detail\nRMSE: {rmse_rf:.4f}°C')
    plt.xlabel('Time Steps')
    plt.ylabel('Temperature (°C)')
    plt.legend()
    plt.grid(True)

    # Plot 5: RF Error Distribution
    plt.subplot(2, 3, 5)
    errors_rf = (y_test_actual - y_pred_rf).flatten()
    plt.hist(errors_rf, bins=50, edgecolor='black', alpha=0.7, color='green')
    plt.title(f'RF Error Distribution\n(Mean: {errors_rf.mean():.4f}°C, Std: {errors_rf.std():.4f}°C)')
    plt.xlabel('Prediction Error (°C)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)

    # Plot 6: NB Error Distribution
    plt.subplot(2, 3, 6)
    errors_nb = (y_test_actual - y_pred_nb).flatten()
    plt.hist(errors_nb, bins=50, edgecolor='black', alpha=0.7, color='orange')
    plt.title(f'NB Error Distribution\n(Mean: {errors_nb.mean():.4f}°C, Std: {errors_nb.std():.4f}°C)')
    plt.xlabel('Prediction Error (°C)')
    plt.ylabel('Frequency')
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'temperature_prediction_comparison.png'), dpi=150, bbox_inches='tight')
    print("Saved: plots/temperature_prediction_comparison.png")
    plt.close()

    # Use best model for forecasting
    if rmse_rf < rmse_nb:
        model_used = "Random Forest"
        best_model = rf_model
        rmse = rmse_rf
        mae = mae_rf
    else:
        model_used = "Naive Bayes"
        best_model = nb_model
        rmse = rmse_nb
        mae = mae_nb

# Create a simple prediction example for next 24 hours
print("\n[INFO] Generating 24-hour temperature forecast...")

# Use last sequence from test set
last_sequence = X_test[-1:].copy()
future_predictions = []

# Predict next 48 steps (24 hours at 30-min intervals)
# Use the best performing model for forecasting
if lstm_available and lstm_model is not None:
    # Use LSTM model for forecasting
    for _ in range(48):
        next_pred = lstm_model.predict(last_sequence, verbose=0)
        future_predictions.append(next_pred[0, 0])
        # Update sequence with new prediction
        last_sequence = np.append(last_sequence[:, 1:, :], next_pred.reshape(1, 1, 1), axis=1)
else:
    # Determine which traditional ML model to use based on performance
    if rmse_rf <= rmse_nb:
        # Use Random Forest for forecasting
        print("   Using Random Forest for forecasting...")
        for _ in range(48):
            last_sequence_flat = last_sequence.reshape(1, -1)
            next_pred = rf_model.predict(last_sequence_flat)
            future_predictions.append(next_pred[0])
            # Update sequence
            last_sequence = np.append(last_sequence[:, 1:], next_pred.reshape(1, 1, 1), axis=1)
    else:
        # Use improved Naive Bayes with temporal features for forecasting
        print("   Using Reactive Naive Bayes for forecasting...")
        for _ in range(48):
            last_sequence_flat = last_sequence.reshape(1, -1)
            # Extract temporal features for this sequence
            temporal_features = extract_temporal_features(last_sequence_flat, seq_length)
            # Get probability distribution over bins
            pred_proba = nb_model.predict_proba(temporal_features)
            # Weighted prediction
            next_pred_binned = np.dot(pred_proba, bin_centers[:pred_proba.shape[1]])
            future_predictions.append(next_pred_binned[0])
            # Update sequence with new prediction
            last_sequence = np.append(last_sequence[:, 1:], next_pred_binned.reshape(1, 1, 1), axis=1)

# Inverse transform future predictions
future_predictions = scaler.inverse_transform(np.array(future_predictions).reshape(-1, 1))

# Plot 24-hour forecast
plt.figure(figsize=(12, 5))
hours = np.arange(0, 24, 0.5)
plt.plot(hours, future_predictions, marker='o', markersize=3, linewidth=2)
plt.title(f'24-Hour Temperature Forecast ({model_used})')
plt.xlabel('Hours from Now')
plt.ylabel('Predicted Temperature (°C)')
plt.grid(True, alpha=0.3)
plt.axhline(y=future_predictions.mean(), color='r', linestyle='--',
            label=f'Mean: {future_predictions.mean():.2f}°C')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, 'temperature_forecast_24h.png'), dpi=150, bbox_inches='tight')
print("Saved: plots/temperature_forecast_24h.png")
plt.close()

print("\n24-Hour Forecast Summary:")
print(f"  Current (estimated): {future_predictions[0][0]:.2f}°C")
print(f"  +6 hours: {future_predictions[12][0]:.2f}°C")
print(f"  +12 hours: {future_predictions[24][0]:.2f}°C")
print(f"  +18 hours: {future_predictions[36][0]:.2f}°C")
print(f"  +24 hours: {future_predictions[47][0]:.2f}°C")
print(f"  Average: {future_predictions.mean():.2f}°C")
print(f"  Range: {future_predictions.min():.2f}°C to {future_predictions.max():.2f}°C")

# =============================================================================
# FINAL SUMMARY & RECOMMENDATIONS
# =============================================================================
print("\n" + "="*70)
print(" " * 15 + "MODEL COMPARISON & RECOMMENDATIONS")
print("="*70)

# Print comparison table
print("\n{:<20} {:<15} {:<15} {:<15}".format("Metric", "LSTM", "Random Forest", "Naive Bayes"))
print("-" * 80)
if lstm_available:
    print("{:<20} {:<15.4f} {:<15.4f} {:<15.4f}".format("RMSE (°C)", rmse_lstm, rmse_rf, rmse_nb))
    print("{:<20} {:<15.4f} {:<15.4f} {:<15.4f}".format("MAE (°C)", mae_lstm, mae_rf, mae_nb))
    print("{:<20} {:<15.2f} {:<15.2f} {:<15.2f}".format("Training Time (s)", training_time_lstm, training_time_rf, training_time_nb))
    print("{:<20} {:<15.3f} {:<15.3f} {:<15.3f}".format("Inference (ms)", inference_time_lstm, inference_time_rf, inference_time_nb))
    print("{:<20} {:<15.2f} {:<15.2f} {:<15.2f}".format("Model Size (MB)", model_size_lstm, model_size_rf, model_size_nb))
else:
    print("{:<20} {:<15} {:<15.4f} {:<15.4f}".format("RMSE (°C)", "N/A", rmse_rf, rmse_nb))
    print("{:<20} {:<15} {:<15.4f} {:<15.4f}".format("MAE (°C)", "N/A", mae_rf, mae_nb))
    print("{:<20} {:<15} {:<15.2f} {:<15.2f}".format("Training Time (s)", "N/A", training_time_rf, training_time_nb))
    print("{:<20} {:<15} {:<15.3f} {:<15.3f}".format("Inference (ms)", "N/A", inference_time_rf, inference_time_nb))
    print("{:<20} {:<15} {:<15.2f} {:<15.2f}".format("Model Size (MB)", "N/A", model_size_rf, model_size_nb))

print("="*80)

# Recommendations
print("\nANALYSIS & RECOMMENDATIONS:")
print("-" * 70)

if lstm_available:
    # All three models were trained
    best_rmse = min(rmse_lstm, rmse_rf, rmse_nb)
    if best_rmse == rmse_lstm:
        better_model = "LSTM"
        second_best = "Random Forest" if rmse_rf < rmse_nb else "Naive Bayes"
        worst_model = "Naive Bayes" if rmse_rf < rmse_nb else "Random Forest"
    elif best_rmse == rmse_rf:
        better_model = "Random Forest"
        second_best = "LSTM" if rmse_lstm < rmse_nb else "Naive Bayes"
        worst_model = "Naive Bayes" if rmse_lstm < rmse_nb else "LSTM"
    else:
        better_model = "Naive Bayes"
        second_best = "LSTM" if rmse_lstm < rmse_rf else "Random Forest"
        worst_model = "Random Forest" if rmse_lstm < rmse_rf else "LSTM"

    print(f"\nBest Accuracy: {better_model} (RMSE: {best_rmse:.4f}°C)")
    print(f"   Ranking: {better_model} > {second_best} > {worst_model}")

    if better_model == "LSTM":
        rf_diff = ((rmse_rf - rmse_lstm) / rmse_rf) * 100
        nb_diff = ((rmse_nb - rmse_lstm) / rmse_nb) * 100
        print(f"   LSTM is {rf_diff:.1f}% more accurate than Random Forest")
        print(f"   LSTM is {nb_diff:.1f}% more accurate than Naive Bayes")
    elif better_model == "Random Forest":
        lstm_diff = ((rmse_lstm - rmse_rf) / rmse_lstm) * 100 if lstm_available else 0
        nb_diff = ((rmse_nb - rmse_rf) / rmse_nb) * 100
        if lstm_available:
            print(f"   Random Forest is {lstm_diff:.1f}% more accurate than LSTM")
        print(f"   Random Forest is {nb_diff:.1f}% more accurate than Naive Bayes")
    else:
        lstm_diff = ((rmse_lstm - rmse_nb) / rmse_lstm) * 100 if lstm_available else 0
        rf_diff = ((rmse_rf - rmse_nb) / rmse_rf) * 100
        if lstm_available:
            print(f"   Naive Bayes is {lstm_diff:.1f}% more accurate than LSTM")
        print(f"   Naive Bayes is {rf_diff:.1f}% more accurate than Random Forest")

    print("\nRECOMMENDATION FOR IoT DEPLOYMENT:")
    print("-" * 70)

    # Decision logic
    if rmse_lstm < rmse_rf * 0.9:  # LSTM significantly better
        print("RECOMMENDED: LSTM")
        print("   Reasons:")
        print("   • Significantly better accuracy")
        print("   • Better captures temporal patterns")
        print("   • Worth the extra computational cost")
        print("\n   Considerations:")
        print("   • Requires TensorFlow runtime")
        print("   • Larger model size")
        print("   • Slightly slower inference")

    elif rmse_rf < rmse_lstm * 0.9:  # RF significantly better
        print("RECOMMENDED: Random Forest")
        print("   Reasons:")
        print("   • Better or comparable accuracy")
        print("   • Much smaller model size")
        print("   • Faster inference time")
        print("   • Easier deployment (no TensorFlow needed)")
        print("\n   Perfect for resource-constrained IoT devices!")

    else:  # Similar performance
        print("RECOMMENDED: Random Forest")
        print("   Reasons:")
        print("   • Similar accuracy to LSTM")
        print(f"   • {((model_size_lstm - model_size_rf) / model_size_lstm * 100):.1f}% smaller model size")
        print(f"   • {((inference_time_lstm - inference_time_rf) / inference_time_lstm * 100):.1f}% faster inference")
        print("   • No TensorFlow dependency")
        print("   • Easier to deploy and maintain")
        print("\n   LSTM could be used if accuracy is critical and resources allow")

else:
    # Only traditional ML models available (RF and NB)
    if rmse_rf < rmse_nb:
        better_model = "Random Forest"
        improvement = ((rmse_nb - rmse_rf) / rmse_nb) * 100
        print("RECOMMENDED: Random Forest (TensorFlow not available)")
        print(f"   • {improvement:.1f}% more accurate than Naive Bayes")
        print(f"   • Fast inference: {inference_time_rf:.3f}ms per prediction")
        print(f"   • Compact model: {model_size_rf:.2f}MB")
        print("   • No heavy dependencies required")
    else:
        better_model = "Naive Bayes"
        improvement = ((rmse_rf - rmse_nb) / rmse_rf) * 100
        print("RECOMMENDED: Naive Bayes (TensorFlow not available)")
        print(f"   • {improvement:.1f}% more accurate than Random Forest")
        print(f"   • Extremely fast inference: {inference_time_nb:.3f}ms per prediction")
        print(f"   • Very compact model: {model_size_nb:.2f}MB")
        print("   • Simplest implementation for IoT devices")

print("\n" + "="*70)
print("SUCCESS: Script completed successfully!")
print("="*70)
print("\nGenerated files:")
print("  Plots (in plots/):")
print("     - plots/lab_iaq_overall.png")
print("     - plots/room_iaq_comparison.png")
print("     - plots/lab_thermal_comfort.png")
print("     - plots/room_thermal_comfort.png")
if lstm_available:
    print("     - plots/temperature_prediction_comparison.png")
else:
    print("     - plots/temperature_prediction_rf.png")
print("     - plots/temperature_forecast_24h.png")
print("\n  Models:")
if lstm_available:
    print("     - temperature_lstm_model.h5")
print("     - temperature_rf_model.joblib")
print("     - temperature_nb_model.joblib")
print("     - temperature_scaler.joblib")
print("="*70)


