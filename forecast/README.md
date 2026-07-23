# forecast/ (not yet built)

Day-ahead demand and generation forecasting, so the settlement engine
can price a portfolio *before* actual half-hourly outturn data exists
for that period -- which is the situation any real supplier is in.

Planned approach: a simple seasonal baseline (day-of-week x
settlement-period averages from `ingestion`'s stored history) as the
first cut, then a gradient-boosted model (`lightgbm`) once there's
enough historical data collected to make that worthwhile. Deliberately
starting simple -- a baseline that's easy to reason about beats an
opaque model with unclear failure modes, and it gives something to
benchmark the fancier model against later.
