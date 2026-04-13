# PPT Review Agent v0.1

An agent that reviews business presentations the way a McKinsey partner would: slide-by-slide redlines plus a deck-level narrative note.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your GEMINI_API_KEY
```

## Download dataset

```bash
python3 data/download.py          # all PDF decks
python3 data/download.py <id>     # one specific deck
```

## Run

```bash
python3 eval.py                           # review all decks
python3 eval.py --deck <deck_id>          # one deck (for testing)
python3 eval.py --reflexion runs/<prior>  # reflexion run after rating a baseline
```

## Rate the output

Open `runs/<timestamp>/ratings.json`. For each slide the agent commented on, change `null` to `true` (agent feedback was correct) or `false` (it was wrong). Add free-form notes per deck.

## Score

```bash
python3 score.py runs/<timestamp>
```

## Config

Edit `config.toml` to change model, thinking level, or iteration budget.
Edit `system_prompt.md` to improve the rubric — no code changes needed.

## Workflow

```
data/download.py → eval.py → rate ratings.json → score.py
                           ↑                           ↓
                    eval.py --reflexion ←──────────────┘
```
