/*
 * Example usage of temperature_model.h in Contiki-NG node
 *
 * This demonstrates how to predict future temperature using
 * the embedded Random Forest model with proper type conversions.
 */

#include "temperature_model.h"
#include <stdio.h>

// Example: Predict next temperature based on last 24 hours
static float predict_next_temperature(void) {{
    // Buffer to store last 48 temperature readings (24 hours at 30-min intervals)
    static float temperature_history[TEMP_MODEL_SEQUENCE_LENGTH];
    static int history_index = 0;
    static int history_filled = 0;

    // Current temperature reading (replace with actual sensor reading)
    float current_temp = (float)temperatureCelsius;

    // Add current reading to history
    temperature_history[history_index] = current_temp;
    history_index = (history_index + 1) % TEMP_MODEL_SEQUENCE_LENGTH;

    if (!history_filled && history_index == 0) {{
        history_filled = 1; // Buffer is now full
    }}

    // Only predict if we have enough history
    if (!history_filled) {{
        return current_temp; // Not enough data yet, return current temp
    }}

    // Rearrange buffer to have oldest reading first
    float ordered_history[TEMP_MODEL_SEQUENCE_LENGTH];
    for (int i = 0; i < TEMP_MODEL_SEQUENCE_LENGTH; i++) {{
        int idx = (history_index + i) % TEMP_MODEL_SEQUENCE_LENGTH;
        ordered_history[i] = temperature_history[idx];
    }}

    // Predict next temperature (handles conversion internally)
    float predicted_temp = temperature_model_predict_celsius(ordered_history);

    printf("Temperature Prediction:\n");
    printf("  Current: %.2f°C\n", current_temp);
    printf("  Predicted (next 30min): %.2f°C\n", predicted_temp);
    printf("  Trend: %s%.2f°C\n",
        predicted_temp > current_temp ? "+" : "",
        predicted_temp - current_temp);

    return predicted_temp;
}}

// Alternative: Manual prediction with direct int16_t conversion
static float predict_temperature_manual(const float *past_48_readings) {{
    int16_t scaled_features[TEMP_MODEL_SEQUENCE_LENGTH];

    // Manually scale and convert to int16_t
    for (int i = 0; i < TEMP_MODEL_SEQUENCE_LENGTH; i++) {{
        float scaled = (past_48_readings[i] - TEMP_SCALER_MIN) / TEMP_SCALER_RANGE;
        scaled_features[i] = (int16_t)(scaled * 32767.0f);
    }}

    // Call model directly
    float scaled_prediction = temperature_model_predict(scaled_features, TEMP_MODEL_SEQUENCE_LENGTH);

    // Convert back to Celsius
    return scaled_prediction * TEMP_SCALER_RANGE + TEMP_SCALER_MIN;
}}

// Simplified: Use the high-level helper function
static float predict_temperature_simple(const float *past_48_readings) {{
    // This function handles all conversions internally
    return temperature_model_predict_celsius(past_48_readings);
}}
