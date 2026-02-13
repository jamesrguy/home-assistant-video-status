# Video Status for Home Assistant

A custom Home Assistant integration that turns any RTSP camera into a state sensor using trainable image recognition. Point it at a garage door, gate, blinds, or anything else with visually distinct states and it will report what it sees.

## Features

- **On-device inference** — histogram and structural feature classifier that runs locally with zero cloud dependencies. Needs only ~50-200ms per frame on ARM hardware.
- **API inference** — send frames to any vision model on [OpenRouter](https://openrouter.ai) (Gemini Flash, GPT-4V, Claude, etc.) for zero-shot classification without training.
- **RTSP authentication** — optional username/password fields, percent-encoded and injected at runtime. Credentials never appear in logs.
- **HACS compatible** — install via the Home Assistant Community Store.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant UI.
2. Go to **Integrations** → three-dot menu → **Custom repositories**.
3. Add this repository URL and select category **Integration**.
4. Search for "Video Status" and install.
5. Restart Home Assistant.

### Manual

Copy `custom_components/video_status/` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Video Status**.
3. Fill in the configuration form:

| Field | Description |
|---|---|
| **Name** | Friendly name for this monitor (e.g. "Garage Door") |
| **RTSP Stream URL** | The stream URL *without* credentials, e.g. `rtsp://192.168.1.100:554/stream` |
| **Username** | *(optional)* Camera username |
| **Password** | *(optional)* Camera password |
| **Inference Mode** | `On-Device (Local)` or `API (OpenRouter)` |
| **States** | Comma-separated list of states to detect, e.g. `open,closed,partial` |
| **Scan Interval** | Seconds between frame captures (5–3600) |

If you chose **API** mode you will be prompted for your OpenRouter API key and model ID on the next step.

## Entities

Each configured camera creates a **device** with two sensors:

| Entity | Type | Description |
|---|---|---|
| **Status** | `sensor` | The detected state name (e.g. `open`, `closed`). Shows `untrained` until a local model is trained. |
| **Confidence** | `sensor` | Classification confidence as a percentage (0–100 %). |

The Status sensor also exposes these **attributes**:

- `scores` — probability for every configured state
- `model_ready` — whether a trained model is loaded
- `available_states` — list of configured states
- `inference_mode` — `local` or `api`
- `training_path` — filesystem path to the training image folder

---

## Local Training Guide

The on-device classifier learns to distinguish your configured states from example images you provide. It uses colour histograms, spatial colour averages, and edge features — no GPU or heavy ML framework required.

### How It Works

1. You capture or supply example images for each state.
2. The classifier extracts a 208-dimension feature vector from each image.
3. It computes the average (centroid) feature vector per state.
4. At inference time it compares a live frame to each centroid using cosine similarity and picks the closest match.

This works well for **fixed-camera** scenarios where the states are visually distinct (different colours, shapes, or positions).

### Step 1 — Find Your Config Entry ID

You need the config entry ID to call the training services. Find it at:

**Settings → Devices & Services → Video Status** → click the entry → look at the URL:

```
/config/integrations/integration/video_status#/entry/<ENTRY_ID>
```

Or read it from the Status sensor's attributes in **Developer Tools → States** — look for any `sensor.video_status_*` entity.

You can also find it via the CLI:

```bash
cat config/.storage/core.config_entries | python3 -c "
import json, sys
entries = json.load(sys.stdin)['data']['entries']
for e in entries:
    if e['domain'] == 'video_status':
        print(f\"{e['title']}: {e['entry_id']}\")
"
```

### Step 2 — Collect Training Images

You have two options:

#### Option A — Capture samples via the service (recommended)

Use the `video_status.capture_sample` service to grab a live frame from the camera and save it directly into the right training folder.

Go to **Developer Tools → Services** and call:

```yaml
service: video_status.capture_sample
data:
  entry_id: "<YOUR_ENTRY_ID>"
  state: "open"
```

Repeat several times for each state. Aim for **10–20 images per state**, captured at different times of day to cover lighting variation.

**Tip:** Set your garage door / gate / blinds to the target state, then call the service a few times across morning, midday, and evening.

You can also automate bulk capture with a script:

```yaml
# configuration.yaml
script:
  capture_garage_open:
    alias: "Capture garage OPEN samples"
    sequence:
      - repeat:
          count: 5
          sequence:
            - service: video_status.capture_sample
              data:
                entry_id: "<YOUR_ENTRY_ID>"
                state: "open"
            - delay: "00:00:03"
```

#### Option B — Drop images into the training folder manually

The integration creates a training directory at:

```
<HA config>/video_status/<ENTRY_ID>/training/
├── open/
├── closed/
└── partial/       # (one folder per configured state)
```

Copy or move `.jpg`, `.jpeg`, `.png`, `.bmp`, or `.webp` images into the appropriate state folder. You can use any source — screenshots, images saved from the camera's web UI, etc.

**Access paths:**

| Install type | Config directory |
|---|---|
| HA OS / Supervised | `/config/video_status/...` (use Samba or SSH add-on) |
| Docker | The path you mounted as `/config` |
| Core | `~/.homeassistant/video_status/...` |

### Step 3 — Train the Model

Call the `video_status.train_model` service:

```yaml
service: video_status.train_model
data:
  entry_id: "<YOUR_ENTRY_ID>"
```

The service will:

1. Read all images from each state sub-folder.
2. Extract features and compute the centroid per state.
3. Save the model to `video_status/<ENTRY_ID>/model.json`.
4. Immediately start classifying live frames.

Check the Home Assistant log for output like:

```
State 'open': trained on 15 images
State 'closed': trained on 12 images
Model saved to /config/video_status/abc123/model.json
```

The Status sensor will switch from `untrained` to a real state value.

### Step 4 — Verify and Iterate

After training:

1. Open **Developer Tools → States** and find your Status sensor.
2. Physically change the state (e.g. open and close the garage door).
3. Wait for the next scan interval or manually trigger an update.
4. Check that the `state` and `confidence` values look correct.
5. Review the `scores` attribute to see probabilities for all states.

**If accuracy is poor:**

- Add more images (especially for the states that get confused).
- Make sure images cover different lighting conditions.
- Ensure the camera angle hasn't shifted between training and live use.
- Re-train by calling `video_status.train_model` again — it replaces the previous model.

### Training Tips

| Recommendation | Why |
|---|---|
| **10–20 images per state minimum** | More samples give a more robust centroid. |
| **Vary the time of day** | Captures lighting changes (morning sun, night IR mode, etc.). |
| **Keep the camera fixed** | The classifier relies on spatial features — a shifted camera looks like a different scene. |
| **Avoid ambiguous frames** | Don't include images captured mid-transition unless you have a dedicated `in_motion` state. |
| **Re-train after camera changes** | If you reposition the camera, adjust zoom, or change IR settings, collect new samples and re-train. |
| **Balance your classes** | Try to have roughly the same number of images per state. |

### Model Persistence

- The trained model is saved as `video_status/<ENTRY_ID>/model.json` and loads automatically on HA restart.
- Training images are kept in place and never deleted by the integration — you can add more and re-train at any time.
- To start from scratch, delete the contents of the training folders and the `model.json` file, then re-train.

---

## API Mode

When using **API (OpenRouter)** inference mode, no local training is needed. The integration sends each captured JPEG frame to the configured vision model with a prompt listing your configured states.

### Supported Models

Any vision-capable model on OpenRouter works. Recommended:

| Model | Cost per frame | Speed | Notes |
|---|---|---|---|
| `google/gemini-flash-1.5-8b` | ~$0.002 | Fast | Good default, cheapest |
| `google/gemini-flash-1.5` | ~$0.005 | Fast | More capable |
| `anthropic/claude-3.5-sonnet` | ~$0.01 | Medium | High accuracy |
| `openai/gpt-4o-mini` | ~$0.005 | Medium | Good balance |

Set the model ID in the config flow or change it by reconfiguring the integration.

---

## Automations

Use the Status sensor in automations like any other HA sensor:

```yaml
automation:
  - alias: "Alert when garage door opens"
    trigger:
      - platform: state
        entity_id: sensor.garage_door_status
        to: "open"
    action:
      - service: notify.mobile_app
        data:
          title: "Garage Door"
          message: "The garage door just opened."

  - alias: "Auto-close garage after 30 minutes"
    trigger:
      - platform: state
        entity_id: sensor.garage_door_status
        to: "open"
        for: "00:30:00"
    action:
      - service: cover.close_cover
        entity_id: cover.garage_door
```

You can also use the confidence sensor to gate actions:

```yaml
condition:
  - condition: numeric_state
    entity_id: sensor.garage_door_confidence
    above: 80
```

## On-Device vs API — When to Use Which

| Factor | On-Device (Local) | API (OpenRouter) |
|---|---|---|
| Latency | ~50–200 ms | 1–5 s |
| Cost | Free | ~$0.002–0.01/frame |
| Privacy | Frames stay local | Frames sent to cloud |
| Setup | Requires training images | Zero-shot, no training |
| Accuracy | Good for distinct, fixed-camera states | Excellent for complex scenes |
| Network | Works offline | Requires internet |
| RAM | ~10–50 MB | Negligible |

**Use local** when: the camera is fixed, states are visually obvious, you want zero ongoing cost, or you need offline operation.

**Use API** when: states are subtle or complex, you don't want to collect training images, or you need it working immediately.
