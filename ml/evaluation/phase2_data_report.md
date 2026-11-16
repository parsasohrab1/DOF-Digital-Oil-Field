# Phase 2 — Dataset Quality & Suitability Report
Each dataset is analyzed independently. No merging is performed.

## Dataset: C-MAPSS FD001 (NASA Turbofan Degradation)

- **Origin / validity**: NASA C-MAPSS turbofan simulation (public benchmark). SIMULATED engine degradation — NOT field oil/gas measurements. Validated for RUL methodology.
- **Suitable ML task**: Regression — Remaining Useful Life (RUL) prediction from sensor and operating-setting trajectories.
- **Records**: 20,631
- **Columns**: 26
- **Dtypes**: {'unit': 'int64', 'time': 'int64', 'op_set_1': 'float64', 'op_set_2': 'float64', 'op_set_3': 'float64', 's1': 'float64', 's2': 'float64', 's3': 'float64', 's4': 'float64', 's5': 'float64', 's6': 'float64', 's7': 'float64', 's8': 'float64', 's9': 'float64', 's10': 'float64', 's11': 'float64', 's12': 'float64', 's13': 'float64', 's14': 'float64', 's15': 'float64', 's16': 'float64', 's17': 'int64', 's18': 'int64', 's19': 'float64', 's20': 'float64', 's21': 'float64'}
- **Missing values**: none
- **Duplicate rows**: 0
- **Units**: {'time': 'cycles', 'op_set_1/2/3': 'normalized', 's1..s21': 'raw sensor'}
- **Numeric ranges (min/max/mean/std)**:
    - unit: min=1.0 max=100.0 mean=51.5066 std=29.2276
    - time: min=1.0 max=362.0 mean=108.8079 std=68.881
    - op_set_1: min=-0.0087 max=0.0087 mean=-0.0 std=0.0022
    - op_set_2: min=-0.0006 max=0.0006 mean=0.0 std=0.0003
    - op_set_3: min=100.0 max=100.0 mean=100.0 std=0.0
    - s1: min=518.67 max=518.67 mean=518.67 std=0.0
    - s2: min=641.21 max=644.53 mean=642.6809 std=0.5001
    - s3: min=1571.04 max=1616.91 mean=1590.5231 std=6.1311
    - s4: min=1382.25 max=1441.49 mean=1408.9338 std=9.0006
    - s5: min=14.62 max=14.62 mean=14.62 std=0.0
    - s6: min=21.6 max=21.61 mean=21.6098 std=0.0014
    - s7: min=549.85 max=556.06 mean=553.3677 std=0.8851
    - s8: min=2387.9 max=2388.56 mean=2388.0967 std=0.071
    - s9: min=9021.73 max=9244.59 mean=9065.2429 std=22.0829
    - s10: min=1.3 max=1.3 mean=1.3 std=0.0
    - s11: min=46.85 max=48.53 mean=47.5412 std=0.2671
    - s12: min=518.69 max=523.38 mean=521.4135 std=0.7376
    - s13: min=2387.88 max=2388.56 mean=2388.0962 std=0.0719
    - s14: min=8099.94 max=8293.72 mean=8143.7527 std=19.0762
    - s15: min=8.3249 max=8.5848 mean=8.4421 std=0.0375
    - s16: min=0.03 max=0.03 mean=0.03 std=0.0
    - s17: min=388.0 max=400.0 mean=393.2107 std=1.5488
    - s18: min=2388.0 max=2388.0 mean=2388.0 std=0.0
    - s19: min=100.0 max=100.0 mean=100.0 std=0.0
    - s20: min=38.14 max=39.43 mean=38.8163 std=0.1807
    - s21: min=22.8942 max=23.6184 mean=23.2897 std=0.1083
- **Outliers (IQR, top-5 cols)**: {'s9': 1686, 's14': 1543, 's8': 320, 's11': 167, 's3': 165}
- **RUL target stats**: min=0 max=361 mean=107.8
- **Units (engines)**: 100  |  avg cycles/unit: 206
- **Test-set true RUL**: 100 engines, range [7, 145]
- **Sensors with zero variance (non-informative)**: ['s1', 's5', 's10', 's16', 's18', 's19']

## Dataset: CWRU Bearing Fault (Case Western Reserve Univ.)

- **Origin / validity**: CWRU bearing test-rig laboratory data (public benchmark). LABORATORY vibration measurements — not field measurements, but real measured accelerations. 9 time-domain features (max/min/mean/sd/rms/skewness/kurtosis/crest/form) + fault label.
- **Suitable ML task**: Classification — bearing fault type (0=Normal / 1=Inner-Race / 2=Outer-Race / 3=Ball).
- **Records**: 2,300
- **Columns**: 10
- **Dtypes**: {'max': 'float64', 'min': 'float64', 'mean': 'float64', 'sd': 'float64', 'rms': 'float64', 'skewness': 'float64', 'kurtosis': 'float64', 'crest': 'float64', 'form': 'float64', 'fault': 'object'}
- **Missing values**: none
- **Duplicate rows**: 0
- **Label distribution (`fault`)**: {'Ball_007_1': 230, 'Ball_014_1': 230, 'Ball_021_1': 230, 'IR_007_1': 230, 'IR_014_1': 230, 'IR_021_1': 230, 'OR_007_6_1': 230, 'OR_014_6_1': 230, 'OR_021_6_1': 230, 'Normal_1': 230}
- **Units**: {'features': 'time-domain stats of 12.8 kHz DE/FE acceleration'}
- **Numeric ranges (min/max/mean/std)**:
    - max: min=0.1573 max=6.8259 mean=1.5751 std=1.5784
    - min: min=-6.2926 max=-0.1602 mean=-1.551 std=1.6027
    - mean: min=0.0032 max=0.0384 mean=0.0157 std=0.0065
    - sd: min=0.0591 max=1.2566 mean=0.3416 std=0.3053
    - rms: min=0.0611 max=1.2563 mean=0.3423 std=0.3048
    - skewness: min=-1.0899 max=1.0595 mean=-0.0423 std=0.1808
    - kurtosis: min=-0.8038 max=30.3853 mean=2.6644 std=4.4111
    - crest: min=2.4285 max=8.8216 mean=4.1731 std=1.1483
    - form: min=3.4844 max=313.7426 mean=26.5448 std=29.2097
- **Outliers (IQR, top-5 cols)**: {'min': 214, 'kurtosis': 186, 'mean': 182, 'skewness': 139, 'form': 122}

## Dataset: Pump Sensor Data

- **Origin / validity**: Real industrial pump sensor log (public Kaggle dataset). FIELD-like time-series measurements from a water pump with documented breakdown events.
- **Suitable ML task**: Time-series forecasting (LSTM) on a sensor channel AND anomaly detection against machine_status (NORMAL/BROKEN/RECOVERING).
- **Records**: 220,320
- **Columns**: 55
- **Dtypes**: {'Unnamed: 0': 'int64', 'timestamp': 'object', 'sensor_00': 'float64', 'sensor_01': 'float64', 'sensor_02': 'float64', 'sensor_03': 'float64', 'sensor_04': 'float64', 'sensor_05': 'float64', 'sensor_06': 'float64', 'sensor_07': 'float64', 'sensor_08': 'float64', 'sensor_09': 'float64', 'sensor_10': 'float64', 'sensor_11': 'float64', 'sensor_12': 'float64', 'sensor_13': 'float64', 'sensor_14': 'float64', 'sensor_15': 'float64', 'sensor_16': 'float64', 'sensor_17': 'float64', 'sensor_18': 'float64', 'sensor_19': 'float64', 'sensor_20': 'float64', 'sensor_21': 'float64', 'sensor_22': 'float64', 'sensor_23': 'float64', 'sensor_24': 'float64', 'sensor_25': 'float64', 'sensor_26': 'float64', 'sensor_27': 'float64', 'sensor_28': 'float64', 'sensor_29': 'float64', 'sensor_30': 'float64', 'sensor_31': 'float64', 'sensor_32': 'float64', 'sensor_33': 'float64', 'sensor_34': 'float64', 'sensor_35': 'float64', 'sensor_36': 'float64', 'sensor_37': 'float64', 'sensor_38': 'float64', 'sensor_39': 'float64', 'sensor_40': 'float64', 'sensor_41': 'float64', 'sensor_42': 'float64', 'sensor_43': 'float64', 'sensor_44': 'float64', 'sensor_45': 'float64', 'sensor_46': 'float64', 'sensor_47': 'float64', 'sensor_48': 'float64', 'sensor_49': 'float64', 'sensor_50': 'float64', 'sensor_51': 'float64', 'machine_status': 'object'}
- **Missing values**: {'sensor_00': 10208, 'sensor_01': 369, 'sensor_02': 19, 'sensor_03': 19, 'sensor_04': 19, 'sensor_05': 19, 'sensor_06': 4798, 'sensor_07': 5451, 'sensor_08': 5107, 'sensor_09': 4595, 'sensor_10': 19, 'sensor_11': 19, 'sensor_12': 19, 'sensor_13': 19, 'sensor_14': 21, 'sensor_15': 220320, 'sensor_16': 31, 'sensor_17': 46, 'sensor_18': 46, 'sensor_19': 16, 'sensor_20': 16, 'sensor_21': 16, 'sensor_22': 41, 'sensor_23': 16, 'sensor_24': 16, 'sensor_25': 36, 'sensor_26': 20, 'sensor_27': 16, 'sensor_28': 16, 'sensor_29': 72, 'sensor_30': 261, 'sensor_31': 16, 'sensor_32': 68, 'sensor_33': 16, 'sensor_34': 16, 'sensor_35': 16, 'sensor_36': 16, 'sensor_37': 16, 'sensor_38': 27, 'sensor_39': 27, 'sensor_40': 27, 'sensor_41': 27, 'sensor_42': 27, 'sensor_43': 27, 'sensor_44': 27, 'sensor_45': 27, 'sensor_46': 27, 'sensor_47': 27, 'sensor_48': 27, 'sensor_49': 27, 'sensor_50': 77017, 'sensor_51': 15383}
- **Duplicate rows**: 0
- **Label distribution (`machine_status`)**: {'NORMAL': 205836, 'RECOVERING': 14477, 'BROKEN': 7}
- **Units**: {'sensor_00..51': 'raw sensor readings', 'timestamp': 'ISO datetime'}
- **Numeric ranges (min/max/mean/std)**:
    - Unnamed: 0: min=0.0 max=220319.0 mean=110159.5 std=63601.05
    - sensor_00: min=0.0 max=2.549 mean=2.3722 std=0.4122
    - sensor_01: min=0.0 max=56.7274 mean=47.5916 std=3.2967
    - sensor_02: min=33.1597 max=56.033 mean=50.8674 std=3.6668
    - sensor_03: min=31.6406 max=48.2205 mean=43.7525 std=2.4189
    - sensor_04: min=2.798 max=800.0 mean=590.6739 std=144.0239
    - sensor_05: min=0.0 max=99.9999 mean=73.3964 std=17.2982
    - sensor_06: min=0.0145 max=22.2512 mean=13.5015 std=2.1637
    - sensor_07: min=0.0 max=23.5966 mean=15.8432 std=2.2012
    - sensor_08: min=0.0289 max=24.349 mean=15.2007 std=2.0374
    - sensor_09: min=0.0 max=25.0 mean=14.7992 std=2.092
    - sensor_10: min=0.0 max=76.1069 mean=41.4703 std=12.0935
    - sensor_11: min=0.0 max=60.0 mean=41.9183 std=13.0564
    - sensor_12: min=0.0 max=45.0 mean=29.137 std=10.1139
    - sensor_13: min=0.0 max=31.1876 mean=7.0789 std=6.9018
    - sensor_14: min=32.4096 max=500.0 mean=376.86 std=113.2064
    - sensor_15: min=nan max=nan mean=nan std=nan
    - sensor_16: min=0.0 max=739.7415 mean=416.4729 std=126.0726
    - sensor_17: min=0.0 max=599.9999 mean=421.1275 std=129.1562
    - sensor_18: min=0.0 max=4.8732 mean=2.3038 std=0.7659
    - sensor_19: min=0.0 max=878.9179 mean=590.8298 std=199.3458
    - sensor_20: min=0.0 max=448.9079 mean=360.8052 std=101.9741
    - sensor_21: min=95.5277 max=1107.526 mean=796.2259 std=226.6793
    - sensor_22: min=0.0 max=594.0611 mean=459.7928 std=154.5283
    - sensor_23: min=0.0 max=1227.564 mean=922.6093 std=291.8353
    - sensor_24: min=0.0 max=1000.0 mean=556.2354 std=182.298
    - sensor_25: min=0.0 max=839.575 mean=649.1448 std=220.8652
    - sensor_26: min=43.1548 max=1214.42 mean=786.4118 std=246.6636
    - sensor_27: min=0.0 max=2000.0 mean=501.5066 std=169.8232
    - sensor_28: min=4.3193 max=1841.146 mean=851.6903 std=313.074
    - sensor_29: min=0.6366 max=1466.281 mean=576.1953 std=225.7641
    - sensor_30: min=0.0 max=1600.0 mean=614.5964 std=195.7269
    - sensor_31: min=23.9583 max=1800.0 mean=863.3231 std=283.5448
    - sensor_32: min=0.2407 max=1839.211 mean=804.2839 std=260.6024
    - sensor_33: min=6.4606 max=1578.6 mean=486.406 std=150.7518
    - sensor_34: min=54.8824 max=425.5498 mean=234.9718 std=88.3761
    - sensor_35: min=0.0 max=694.4791 mean=427.1298 std=141.7725
    - sensor_36: min=2.261 max=984.0607 mean=593.0339 std=289.3855
    - sensor_37: min=0.0 max=174.9012 mean=60.7874 std=37.6049
    - sensor_38: min=24.4792 max=417.7083 mean=49.6559 std=10.5404
    - sensor_39: min=19.2708 max=547.9166 mean=36.6104 std=15.6137
    - sensor_40: min=23.4375 max=512.7604 mean=68.8445 std=21.3711
    - sensor_41: min=20.8333 max=420.3125 mean=35.3651 std=7.8987
    - sensor_42: min=22.1354 max=374.2188 mean=35.4535 std=10.2595
    - sensor_43: min=24.4792 max=408.5937 mean=43.8796 std=11.0444
    - sensor_44: min=25.7523 max=1000.0 mean=42.6569 std=11.5764
    - sensor_45: min=26.331 max=320.3125 mean=43.095 std=12.8375
    - sensor_46: min=26.331 max=370.3704 mean=48.0186 std=15.6413
    - sensor_47: min=27.1991 max=303.5301 mean=44.3409 std=10.4424
    - sensor_48: min=26.331 max=561.632 mean=150.889 std=82.245
    - sensor_49: min=26.6204 max=464.4097 mean=57.12 std=19.1436
    - sensor_50: min=27.4884 max=1000.0 mean=183.0493 std=65.2587
    - sensor_51: min=27.7778 max=1000.0 mean=202.6997 std=109.5886
- **Outliers (IQR, top-5 cols)**: {'sensor_09': 68761, 'sensor_20': 59580, 'sensor_14': 58154, 'sensor_19': 58108, 'sensor_21': 56063}
- **Time span**: 2018-04-01 00:00:00 → 2018-08-31 23:59:00  (152 days)

## Dataset: ESP Features (vibration-derived, ESPset)

- **Origin / validity**: Features extracted from ESP (Electrical Submersible Pump) vibration signals. 11 ESPs labelled with real fault classes.
- **Suitable ML task**: Multi-class classification — ESP fault type (Normal / Unbalance / Faulty sensor / Rubbing / Misalignment).
- **Records**: 6,032
- **Columns**: 10
- **Dtypes**: {'id': 'int64', 'esp_id': 'int64', 'label': 'object', 'median(8,13)': 'float64', 'rms(98,102)': 'float64', 'median(98,102)': 'float64', 'peak1x': 'float64', 'peak2x': 'float64', 'a': 'float64', 'b': 'float64'}
- **Missing values**: none
- **Duplicate rows**: 0
- **Label distribution (`label`)**: {'Normal': 4801, 'Unbalance': 576, 'Faulty sensor': 295, 'Rubbing': 290, 'Misalignment': 70}
- **Units**: {'features': 'vibration statistical features (rms, median, peak, fit coeffs)'}
- **Numeric ranges (min/max/mean/std)**:
    - id: min=0.0 max=6031.0 mean=3015.5 std=1741.4327
    - esp_id: min=0.0 max=10.0 mean=5.2769 std=3.0211
    - median(8,13): min=0.0 max=2.4286 mean=0.0092 std=0.0756
    - rms(98,102): min=0.0 max=2.2219 mean=0.1566 std=0.1523
    - median(98,102): min=0.0 max=0.0748 mean=0.0018 std=0.0027
    - peak1x: min=0.0 max=0.5703 mean=0.0794 std=0.0637
    - peak2x: min=0.0 max=0.0648 mean=0.0074 std=0.0073
    - a: min=-0.0164 max=0.0023 mean=-0.0007 std=0.0012
    - b: min=-14.4688 max=1.6646 mean=-6.223 std=1.2999
- **Outliers (IQR, top-5 cols)**: {'median(8,13)': 675, 'a': 487, 'b': 433, 'median(98,102)': 320, 'peak2x': 310}
- **ESPs (esp_id)**: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

## ERROR analyzing analyze_sorush

```
ValueError: Length mismatch: Expected axis has 0 elements, new values have 7 elements
```