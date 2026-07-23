# frontend/ (not yet built)

React + Tailwind dashboard. Planned interaction: pick a business type
and a generation mix, watch the itemised bill (from `api/`'s `/settle`
endpoint) update live, with the computed price plotted against the real
Octopus Agile rate and the Ofgem price cap for the same period.

The point of this piece isn't visual polish -- it's letting someone
who isn't going to read the Rust source *feel* how much of a bill is
generation cost vs. network charges vs. policy costs vs. margin, and
how that shifts as the renewable share of the portfolio changes.
