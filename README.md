# Ghost Load 👻⚡

Finds the "ghosts" in your electricity use (always-on devices, mystery night-time
spikes, one-off surges) and lets a **local open-weight model** (Gemma via Ollama)
tell each one as a short ghost story. Your data never leaves your computer.

## Run it
```bash
# 1. one-time: install Ollama (ollama.com), then
ollama pull gemma3:1b          # fast; or gemma3:4b for better stories

# 2. make sample data (or use your own CSV with columns: timestamp,kwh)
python3 generate_data.py

# 3. detect ghosts (plain code, no AI)
python3 detect.py data/sample_usage.csv --rate 0.30

# 4. tell the stories (local AI)
python3 story.py findings.json --model gemma3:1b
```
Use your own tariff for `--rate`. The default 0.30 is only an assumption.
