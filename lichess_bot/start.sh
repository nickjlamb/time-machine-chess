#!/bin/sh
# Entrypoint for a Time-Machine Chess Lichess BOT account.
#
#   TMC_ERA            which era this account plays (default: romantic)
#   LICHESS_BOT_TOKEN  personal API token with the bot:play scope (required)
#
# The image bakes in the pilot era's checkpoint; any other era is fetched on
# first boot, so the same image can serve all five accounts.
set -e

ERA="${TMC_ERA:-romantic}"
echo "[start] Time-Machine Chess on Lichess — era: ${ERA}"

if [ ! -f "/app/models/${ERA}.pt" ]; then
  echo "[start] ${ERA}.pt not in the image — fetching from the weights release"
  python /app/scripts/fetch_models.py "${ERA}"
fi

# Render config.yml for this era (greetings in period voice) and refuse to
# start on a missing token or an over-length chat line.
python -m lichess_bot.render_config /app/lichess-bot/config.yml

# The framework resolves engine.name against a module called `homemade` in its
# own directory; ours is a three-line adapter over lichess_bot/engine.py.
cp /app/lichess_bot/homemade.py /app/lichess-bot/homemade.py

cd /app/lichess-bot
exec python lichess-bot.py -v
