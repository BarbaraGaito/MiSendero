# WHAMAP Dataset

The WHAMAP dataset contains inertial data collected from a cohort of 10 experimental subjects during physical activities such as walking and squatting, with controlled fatigue progression for some activities, annotated according to the Borg scale.

In particular, the dataset includes the measurements gathered with five wearable IMU devices (WT9011DCL-BT50) connected via Bluetooth Low Energy (BLE), each embedding accelerometer, gyroscope and orientation (Euler angles and quaternion) sensors, located on five body locations of the lower limbs (left thigh, right thigh, left shin, right shin and right foot), together with the inertial measurements from the embedded sensors of a smartphone (accelerometer, gyroscope and magnetometer). All measurements are sampled at 50 Hz and exported in CSV (Comma Separated Value) format.

### DATA subdirectory

The `data/` subfolder contains 10 subfolders, each holding all movement traces collected from a particular participant. The participant's numerical identifier is indicated in the subfolder name (`subject_XX`, with `XX` ranging from 01 to 10). Each subfolder contains a unique CSV file for each activity measurement, and the filename identifies the activity performed. The 5 activities are:

| Activity | Description |
|----------|-------------|
| `seating`   | Sitting |
| `stend`     | Standing |
| `walking`   | Walking |
| `uphill`    | Uphill walking |
| `squating`  | Squatting |

Files for the activities `walking`, `uphill` and `squating` may also have a repetition file suffixed with `_B` (for example `walking_B.csv`), which corresponds to a second session performed under a higher level of fatigue. 

### Collection protocol

The data collection was carried out in the following order:

1. **Static activities** were performed first: `stend` (standing) and `seating` (sitting).
2. **Two collection blocks** were then carried out, with the second block being denoted by the `_B` suffix in the file names.
3. In both the first and second blocks, the subjects performed the activities in the following sequence:
   - **`squating`** (squatting) — with fatigue marking every 30 seconds and rest intervals of 1 minute, over 5 sessions;
   - **`walking`** — at a speed of 5 km/h;
   - **`uphill`** — at a speed of 3 km/h.

### CSV trace format

Each line of a trace file contains all measurements taken at a particular instant from all sensors. The measurements in each line, which are separated by commas, are organized in columns as follows:

**Metadata columns (4 columns):**

| Column | Field | Description |
|--------|-------|-------------|
| 1 | `user-id` | Numerical identifier of the participant (`01`–`10`) |
| 2 | `time` | Timestamp of the sample in `HH:MM:SS.ssssss` format |
| 3 | `activity_type` | Name of the activity performed |
| 4 | `f-level` | Fatigue level (0–4), annotated according to the Borg scale |

In the CSV files, the `activity_type` field is stored as a double-quoted string, for example `"seating"`, `"walking"`, `"uphill"` or `"squating"`. All other fields are stored without quotes.

**Sensors 1–5 (WT9011DCL-BT50) columns (13 columns × 5 sensors = 65 columns):**

For each sensor `i` (1–5), 13 columns are provided:

| Group | Columns | Description | Unit |
|-------|---------|-------------|------|
| Acceleration | `sensor{i}_accelX/Y/Z` | Linear acceleration on the X/Y/Z axes | g |
| Gyroscope | `sensor{i}_gyroX/Y/Z` | Angular velocity on the X/Y/Z axes | °/s |
| Euler angles | `sensor{i}_roll/pitch/yaw` | Orientation in Euler angles | ° |
| Quaternion | `sensor{i}_quatW/X/Y/Z` | Orientation as a unit quaternion | — |

**Smartphone columns (9 columns):**

| Column | Description | Unit |
|--------|-------------|------|
| `phone_accelX/Y/Z` | Linear acceleration on the X/Y/Z axes | m/s² |
| `phone_gyroX/Y/Z` | Angular velocity on the X/Y/Z axes | rad/s |
| `phone_magX/Y/Z` | Magnetic field on the X/Y/Z axes | µT |

In total, each CSV line contains **78 columns** (4 metadata + 5 × 13 sensor + 9 phone). When a sensor is not connected or has no data for a sample, its corresponding columns are left empty. 

### Videos

The `videos/` folder includes video clips recorded during the data collection to illustrate the testbed and the monitoring procedure.

## User data

The root folder encompasses an extra file describing the personal characteristics of each experimental subject:

- **`User_data.csv`** — includes the numerical identifier, gender, age, height, weight, footedness, and weekly activity frequency of each participant.
The file contains one row per participant, whose identifier (`subject_XX`) matches the corresponding subfolder under `data/`.