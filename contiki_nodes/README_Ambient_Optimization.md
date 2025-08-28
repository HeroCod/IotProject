# Ambient Light Optimization for Cooja Simulation

## Overview

This implementation adds **ambient light optimization** to the energy-saving IoT lighting system. The system now:

1. **Monitors ambient light levels** (lux sensor readings)
2. **Prevents unnecessary lighting** when ambient light is already sufficient (≥65 lux vs target 70 lux)
3. **Tracks performance metrics** to measure energy savings from ambient optimization

## Key Features Added

### 1. Ambient Light Logic

```c
// In IoT nodes: Enhanced light sensor simulation
light_val = 30 + (random_rand() % 60); // Realistic 30-90 lux range
```

### 2. Optimization Check (Collector)

```python
# Prevent lights ON when ambient light is sufficient
if led_command == "on" and lux >= 65:
    led_command = "off"
    energy_saved += 0.1  # kWh saved
```

### 3. Performance Tracking

- Total decisions made
- Ambient light overrides (prevented unnecessary lighting)
- Energy saved from ambient optimization
- Automatic performance reporting every 50 decisions

## Updated IoT Nodes for Cooja

### Node Differentiation

- **Node1 (Office)**: 30-90 lux, ~67% occupied, moderate energy patterns
- **Node2 (Kitchen)**: 40-90 lux, ~75% occupied, higher energy (appliances)
- **Node3 (Living Room)**: 25-95 lux, ~80% occupied, evening-focused patterns

### Enhanced Sensor Data

```json
{
  "sensor_id": "node1",
  "lux": 65,
  "occupancy": 1,
  "temperature": 24,
  "room_usage": 0.150,
  "solar_surplus": 0.2,
  "cloud_cover": 0.3,
  "visibility": 8.5
}
```

## Performance Impact

### Expected Results in Cooja

- **5-15% of lighting decisions** will be optimized by ambient light detection
- **~0.1 kWh saved per optimization** (preventing unnecessary light activation)
- **Cumulative energy savings** tracked and reported in real-time logs

### Measurement Metrics

1. **Override Rate**: Percentage of "turn ON" commands prevented by sufficient ambient light
2. **Energy Impact**: Total kWh saved by ambient optimization
3. **System Efficiency**: Balance between comfort and energy conservation

## Running in Cooja

### 1. Compile Updated Nodes

```bash
cd contiki_nodes
make TARGET=cooja node1.cooja
make TARGET=cooja node2.cooja  
make TARGET=cooja node3.cooja
```

### 2. Launch System

```bash
./run.sh  # Starts all containers including enhanced collector
```

### 3. Monitor Performance

Watch collector logs for ambient optimization reports:

```markdown
[AMBIENT] Override: on → off (lux=70 sufficient)
[AMBIENT] Stats: 12/50 overrides, 1.20kWh saved
[PERFORMANCE REPORT] Ambient Light Optimization:
  Total decisions: 150
  Ambient overrides: 23 (15.3%)
  Energy saved from ambient optimization: 2.300 kWh
```

### 4. Test Scenarios

The system will automatically test various lighting scenarios:

- **High ambient light + occupancy**: Should prevent unnecessary lighting
- **Low ambient light + occupancy**: Should allow lighting for comfort
- **Empty rooms**: Energy savings prioritized regardless of light levels

## Algorithm Summary

### Energy Saving Priority

1. **Primary**: Turn OFF wasteful lighting (empty rooms, excessive consumption)
2. **Secondary**: Prevent unnecessary lighting (sufficient ambient light)
3. **Comfort**: Maintain lighting when needed for occupant comfort

### Ambient Light Thresholds

- **Target with lights ON**: 70 lux
- **Sufficient ambient threshold**: 65 lux (92% of target)
- **Override logic**: If ambient ≥ 65 lux, don't turn lights ON

This optimization adds an additional layer of energy efficiency while maintaining the core energy-saving functionality of the ML model.
