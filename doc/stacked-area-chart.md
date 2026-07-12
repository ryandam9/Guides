# Stacked Area Chart with `area_chart()`

How to produce a stacked area chart like this — daily rows ingested, split by source, each source stacked as a colored band:

> **Rows ingested by source (stacked)** — `s3` (blue, bottom), `kinesis` (green), `api` (yellow, top), with the total read off the top edge.

All cells below run in `%%local` on a sparkmagic kernel (SageMaker Studio / EMR notebooks), with `setup()` already applied:

```python
%%local
from notebook_style import setup, area_chart
setup()
```

## The shape the chart needs

`area_chart()` wants a **wide** DataFrame: one row per date, one numeric column per series.

| day | s3 | kinesis | api |
|---|---:|---:|---:|
| 2026-06-01 | 4012 | 2688 | 1204 |
| 2026-06-02 | 4090 | 2743 | 1189 |
| ... | ... | ... | ... |

```python
%%local
area_chart(df, x="day", y=["s3", "kinesis", "api"],
           title="Rows ingested by source (stacked)")
```

The `y` list order controls stacking — first column is the bottom band. Colors are assigned from the active palette in the same order.

## Getting real data into that shape

A stacked chart needs **three** dimensions: the x-axis (day), the series (source), and the value (rows). If your DataFrame has only two columns (day + value), there is nothing to stack — see [Only two columns?](#only-two-columns) below.

Aggregate on the cluster, pull a bounded result down with `-o`, pivot locally:

```sql
%%sql -o ingest -n 500
SELECT CAST(date_trunc('day', created_at) AS DATE) AS day,
       source,
       COUNT(*) AS rows
FROM ingestion_log
WHERE created_at >= date_sub(current_date(), 30)
GROUP BY 1, 2
ORDER BY 1
```

```python
%%local
wide = (ingest.pivot(index="day", columns="source", values="rows")
              .fillna(0)
              .reset_index())
wide["day"] = pd.to_datetime(wide["day"])

area_chart(wide, x="day", y=["s3", "kinesis", "api"],
           title="Rows ingested by source (stacked)")
```

If your SQL dialect pivots comfortably, skip the pandas pivot and produce the wide shape in the query itself:

```sql
%%sql -o wide -n 500
SELECT CAST(date_trunc('day', created_at) AS DATE) AS day,
       SUM(CASE WHEN source = 's3'      THEN 1 ELSE 0 END) AS s3,
       SUM(CASE WHEN source = 'kinesis' THEN 1 ELSE 0 END) AS kinesis,
       SUM(CASE WHEN source = 'api'     THEN 1 ELSE 0 END) AS api
FROM ingestion_log
WHERE created_at >= date_sub(current_date(), 30)
GROUP BY 1
ORDER BY 1
```

Values pulled through `-o` can arrive as strings — coerce before plotting if needed:

```python
%%local
for c in ["s3", "kinesis", "api"]:
    wide[c] = pd.to_numeric(wide[c])
```

## Self-contained demo (no cluster needed)

```python
%%local
import numpy as np, pandas as pd
from notebook_style import area_chart

rng = np.random.default_rng(7)
days = pd.date_range("2026-06-01", periods=30)
df = pd.DataFrame({
    "day": days,
    "s3":      4000 + rng.normal(0, 150, 30).cumsum().clip(-500, 1200),
    "kinesis": 2700 + rng.normal(10, 90, 30).cumsum().clip(-400, 1300),
    "api":     1200 + rng.normal(8, 60, 30).cumsum().clip(-300, 900),
})
area_chart(df, x="day", y=["s3", "kinesis", "api"],
           title="Rows ingested by source (stacked)")
```

## Only two columns?

With just a date and a value column there is no series dimension, so nothing stacks. You get the single-series variant — one soft wash, a 2px line, and the last value labeled at the endpoint:

```python
%%local
area_chart(df, x="col1", y="col2", title="Rows ingested")
```

To reach the stacked picture, bring the third dimension into the query (`GROUP BY day, source`) and pivot as shown above.

If the two columns are a **category** and a total (not a time axis), an area chart is the wrong shape — use `bar_chart(df, x="col1", y="col2")` to compare, or `donut_chart(df, labels="col1", values="col2")` for share-of-total.

## Useful knobs

- `stacked=False` — overlaid translucent washes instead of stacking; compares shapes rather than composition (fine for 2 series, muddy beyond that).
- Omit `y` — every numeric column is plotted.
- `colors=["#112233", ...]` — one-off palette for this chart; `chart_palette("bee_eater")` switches all charts notebook-wide.
- The figure is interactive plotly: hover shows every series at the cursor's date; `fig.write_html("chart.html")` exports it.
