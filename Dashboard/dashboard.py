import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import pydeck as pdk
import altair as alt
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib.cm as cm

# ------------------------------------------------------------
# App config
# ------------------------------------------------------------
st.set_page_config(page_title="DeTourism Dashboard", layout="wide")

APP_DIR = Path(__file__).resolve().parent


def find_file(filename: str) -> Path:
    """
    Looks for a file in:
      1) same folder as dashboard.py
      2) repo root (parent folder)
    """
    candidates = [APP_DIR / filename, APP_DIR.parent / filename]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Could not find '{filename}' in: {candidates}")


def safe_image(name: str):
    """
    Display an image if present (same folder or parent).
    """
    try:
        p = find_file(name)
        st.image(Image.open(p), use_container_width=True)
    except Exception:
        st.info(f"(Optional image not found: {name})")


# ------------------------------------------------------------
# Data loaders
# ------------------------------------------------------------
@st.cache_data
def load_pressure_points() -> gpd.GeoDataFrame:
    """
    Expects: test_pressure_time_small.csv
      - geometry: WKT POINT
      - Datetime or datetime column
      - pressure numeric
      - category string
    """
    csv_path = find_file("test_pressure_time_small.csv")
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    if "geometry" not in df.columns:
        raise ValueError("test_pressure_time_small.csv must contain a 'geometry' column (WKT POINT).")

    df["geometry"] = df["geometry"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
    gdf["lat"], gdf["lon"] = gdf.geometry.y, gdf.geometry.x

    if "Datetime" in gdf.columns and "datetime" not in gdf.columns:
        gdf = gdf.rename(columns={"Datetime": "datetime"})
    if "datetime" not in gdf.columns:
        raise ValueError("test_pressure_time_small.csv must contain 'Datetime' or 'datetime' column.")

    gdf["datetime"] = pd.to_datetime(gdf["datetime"])

    if "pressure" not in gdf.columns:
        raise ValueError("test_pressure_time_small.csv must contain a 'pressure' column.")
    if "category" not in gdf.columns:
        gdf["category"] = "All"

    return gdf


@st.cache_data
def load_neighbourhood_polygons() -> gpd.GeoDataFrame:
    """
    Expects: overtourism_neighbourhoods.csv
      - name
      - geometry: WKT POLYGON/MULTIPOLYGON
      - (optional) jaar, pct_nuisance, level
    """
    csv_path = find_file("overtourism_neighbourhoods.csv")
    df = pd.read_csv(csv_path)

    # drop annoying index col if present
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    if "geometry" not in df.columns:
        raise ValueError("overtourism_neighbourhoods.csv must contain a 'geometry' column (WKT).")

    df["geometry"] = df["geometry"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    if "name" not in gdf.columns:
        raise ValueError("overtourism_neighbourhoods.csv must contain a 'name' column.")

    return gdf


@st.cache_data
def load_hotels_all_data() -> pd.DataFrame:
    """
    Expects: hotels_all_data.csv
      - Buurt column (neighbourhood key)
      - many numeric indicator columns
    """
    csv_path = find_file("hotels_all_data.csv")
    df = pd.read_csv(csv_path)

    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    if "Buurt" not in df.columns:
        raise ValueError("hotels_all_data.csv must contain 'Buurt' column.")

    return df


def _norm_name(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip().lower()


@st.cache_data
def build_capacity_polygons() -> gpd.GeoDataFrame:
    """
    1) Load neighbourhood polygons
    2) Aggregate hotel indicators by Buurt (mean)
    3) Join onto polygons by name (normalized)
    """
    poly = load_neighbourhood_polygons().copy()
    hotels = load_hotels_all_data().copy()

    # numeric cols to aggregate
    numeric_cols = [c for c in hotels.columns if pd.api.types.is_numeric_dtype(hotels[c])]
    if not numeric_cols:
        raise ValueError("No numeric columns found in hotels_all_data.csv.")

    agg = hotels.groupby("Buurt")[numeric_cols].mean(numeric_only=True).reset_index()
    agg = agg.rename(columns={"Buurt": "name"})

    poly["_k"] = poly["name"].apply(_norm_name)
    agg["_k"] = agg["name"].apply(_norm_name)

    merged = poly.merge(agg.drop(columns=["name"]), on="_k", how="left").drop(columns=["_k"])
    return merged


def numeric_columns(df: pd.DataFrame, exclude: set[str] | None = None) -> list[str]:
    exclude = exclude or set()
    cols = []
    for c in df.columns:
        if c in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


# ------------------------------------------------------------
# PyDeck helpers
# ------------------------------------------------------------
def add_color_column(gdf: gpd.GeoDataFrame, value_col: str) -> gpd.GeoDataFrame:
    g = gdf.copy()
    v = pd.to_numeric(g[value_col], errors="coerce")

    if v.notna().sum() == 0:
        g["fill_color"] = [[180, 180, 180, 60]] * len(g)
        return g

    vmin = float(np.nanmin(v))
    vmax = float(np.nanmax(v))
    if np.isclose(vmin, vmax):
        g["fill_color"] = [[60, 130, 200, 120]] * len(g)
        return g

    vn = (v - vmin) / (vmax - vmin)
    cmap = cm.get_cmap("viridis")

    colors = []
    for x in vn:
        if np.isnan(x):
            colors.append([180, 180, 180, 60])
        else:
            r, gg, b, _ = cmap(float(x))
            colors.append([int(r * 255), int(gg * 255), int(b * 255), 140])

    g["fill_color"] = colors
    return g


def pydeck_geojson_map(gdf: gpd.GeoDataFrame, tooltip_fields: list[str], zoom: float = 11.7):
    # centroid mean for view
    c = gdf.geometry.centroid
    view_state = pdk.ViewState(latitude=float(c.y.mean()), longitude=float(c.x.mean()), zoom=zoom, pitch=0)

    # tooltip html
    tooltip_html = "<b>{name}</b>"
    for f in tooltip_fields:
        if f == "name":
            continue
        tooltip_html += f"<br>{f}: {{{f}}}"

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=gdf.__geo_interface__,
        pickable=True,
        stroked=True,
        filled=True,
        get_fill_color="properties.fill_color",
        get_line_color=[40, 40, 40, 180],
        line_width_min_pixels=1,
        auto_highlight=True,
    )

    deck = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"html": tooltip_html})
    st.pydeck_chart(deck, use_container_width=True)


# ------------------------------------------------------------
# Pages
# ------------------------------------------------------------
def page_home():
    st.title("DeTourism — Mapping Overtourism Dynamics in Amsterdam")
    st.caption("MSc thesis (TU Delft) • Graduated July 2025 • Public demo dashboard")

    # Optional header image (if you have it)
    safe_image("new Title heatmap.png")

    st.markdown(
        """
Amsterdam is facing increasing pressure from overtourism. While tourism brings economic benefits, it also creates strain on local life:
overcrowded streets, rising nuisance, and pressure on social cohesion.

This dashboard turns public digital traces (e.g., Google Reviews + Popular Times-derived pressure signals) into **spatiotemporal insights**:
**where and when pressure peaks**, and how this relates to urban structure and potential strategies.
        """.strip()
    )

    # Optional supporting image
    safe_image("SCWX2243.jpeg")

    # Load pressure data
    try:
        gdf = load_pressure_points()
    except Exception as e:
        st.error(f"Could not load pressure dataset: {e}")
        st.info("Expected: test_pressure_time_small.csv (WKT points + datetime + pressure + category).")
        return

    st.markdown("### Explore Tourist Pressure")
    st.caption("Use the filters to see how pressure shifts by category and time.")

    # Layout: filters left, map right
    filter_col, map_col = st.columns([1, 3])

    with filter_col:
        st.subheader("Filters")

        categories = sorted(gdf["category"].dropna().unique().tolist())
        # 3-column checkbox grid (like your original)
        chk_cols = st.columns(2)
        selected_cats = []
        for idx, cat in enumerate(categories):
            container = chk_cols[idx % 2]
            if container.checkbox(cat, value=(idx < min(6, len(categories))), key=f"home_cat_{idx}"):
                selected_cats.append(cat)

        if not selected_cats:
            st.warning("Select at least one category.")
            return

        filtered = gdf[gdf["category"].isin(selected_cats)].copy()

        # day/hour based on existing timestamps
        filtered["date"] = filtered["datetime"].dt.date
        filtered["hour"] = filtered["datetime"].dt.hour

        available_days = sorted(filtered["date"].unique())
        selected_day = st.selectbox(
            "Day",
            available_days,
            format_func=lambda d: pd.Timestamp(d).strftime("%A %d %b")
        )

        # IMPORTANT: default hour=16 to avoid empty / boring first view
        selected_hour = st.slider("Hour", 0, 23, 16)

        selected_dt = pd.Timestamp(selected_day) + pd.Timedelta(hours=int(selected_hour))

    with map_col:
        st.subheader("Tourist Pressure Map")

        subset = filtered[filtered["datetime"] == selected_dt].copy()

        if subset.empty:
            st.info("No data for this moment. Try another hour/day or broaden categories.")
        else:
            view = pdk.ViewState(
                latitude=float(subset["lat"].mean()),
                longitude=float(subset["lon"].mean()),
                zoom=12,
                pitch=0
            )

            layer = pdk.Layer(
                "HeatmapLayer",
                data=subset,
                get_position="[lon, lat]",
                get_weight="pressure",
                radiusPixels=60
            )

            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view), use_container_width=True)

    st.subheader("Pressure Over Time")
    ts = filtered.groupby("datetime", as_index=False)["pressure"].mean()
    ts = ts.sort_values("datetime")

    chart = (
        alt.Chart(ts)
        .mark_line()
        .encode(
            x=alt.X("datetime:T", title="Time"),
            y=alt.Y("pressure:Q", title="Average pressure"),
            tooltip=["datetime:T", "pressure:Q"],
        )
        .properties(height=220)
    )
    st.altair_chart(chart, use_container_width=True)

    # Optional image you already use
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.markdown(
            """
**Why this matters**  
Overtourism is not just “too many tourists”. It’s a **dynamic system**: where people go, when they go, and how the urban fabric absorbs them.
To respond effectively, we need to look beyond reactive measures and understand spatial-temporal patterns.
            """.strip()
        )
    with col2:
        safe_image("dining cafes.png")

    safe_image("public transport corridor.png")


def page_carrying_capacity():
    st.title("Carrying Capacity — Urban structure & accessibility indicators")
    st.markdown(
        """
This page maps **neighbourhood-level indicators** derived from the hotel dataset (`hotels_all_data.csv`),
aggregated per neighbourhood (Buurt) and joined to neighbourhood polygons.

Use the dropdown to switch indicators and explore where the city has **higher potential capacity / accessibility**.
        """.strip()
    )

    try:
        gdf = build_capacity_polygons()
    except Exception as e:
        st.error(f"Could not build capacity polygons: {e}")
        st.info("Expected files: overtourism_neighbourhoods.csv + hotels_all_data.csv")
        return

    # Optional year filter (if nuisance is included)
    if "jaar" in gdf.columns:
        years = sorted(pd.to_numeric(gdf["jaar"], errors="coerce").dropna().unique().tolist())
        if len(years) > 1:
            selected_year = st.selectbox("Year (for nuisance overlay columns)", years, index=len(years)-1)
            gdf = gdf[gdf["jaar"] == selected_year].copy()

    exclude = {"jaar"}
    vars_ = numeric_columns(gdf, exclude=exclude)

    # Prefer these columns if present (they are in your hotels_all_data.csv)
    preferred = [
        "pressure 15min",
        "percent_within_15min",
        "15min % high A.C.",
        "pressure 25min",
        "percent_within_25min",
        "25min % high A.C.",
        "pressure 5min",
        "percent_within_5min",
        "5min % high A.C.",
        "pct_nuisance",
    ]

    default_idx = 0
    for p in preferred:
        if p in vars_:
            default_idx = vars_.index(p)
            break

    selected_var = st.selectbox("Choose an indicator to display:", vars_, index=default_idx)

    # Show join quality warning (if the chosen var came from hotels aggregation)
    if selected_var in ["pressure 5min", "pressure 15min", "pressure 25min", "5min % high A.C.", "15min % high A.C.", "25min % high A.C."]:
        miss = pd.to_numeric(gdf[selected_var], errors="coerce").isna().sum()
        if miss > 0:
            st.warning(f"{miss} neighbourhoods have no matching hotel-derived values (name mismatch or no hotels in that neighbourhood).")

    mapped = add_color_column(gdf, selected_var)

    left, right = st.columns([1.2, 0.8])

    with left:
        st.subheader("Indicator Map")
        tooltip_fields = ["name", selected_var]
        if "pct_nuisance" in gdf.columns and selected_var != "pct_nuisance":
            tooltip_fields = ["name", selected_var, "pct_nuisance"]
        pydeck_geojson_map(mapped, tooltip_fields=tooltip_fields, zoom=11.7)

    with right:
        st.subheader("Distribution")
        s = pd.to_numeric(mapped[selected_var], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()

        if s.empty:
            st.warning("No valid values for this indicator.")
        else:
            hist_df = pd.DataFrame({selected_var: s})
            hist = (
                alt.Chart(hist_df)
                .mark_bar()
                .encode(
                    x=alt.X(f"{selected_var}:Q", bin=alt.Bin(maxbins=30)),
                    y=alt.Y("count()", title="Neighbourhoods"),
                    tooltip=["count()"],
                )
                .properties(height=220)
            )
            st.altair_chart(hist, use_container_width=True)

            st.markdown("**Quick stats**")
            st.write(
                {
                    "min": float(s.min()),
                    "median": float(s.median()),
                    "mean": float(s.mean()),
                    "max": float(s.max()),
                }
            )

    with st.expander("How to read these indicators (short)"):
        st.markdown(
            """
- **pressure 5/15/25min**: aggregated pressure signals around hotel catchments (time-based buffers).
- **% high A.C. (Angular Choice)**: proxy for movement centrality / network attractiveness.
- **percent_within_5/15/25min**: how much of the points fall within those catchments.
Use this page to spot **areas with capacity potential** that can support a redistribution strategy.
            """.strip()
        )


def page_detour():
    st.title("The DeTour — A corridor strategy to redistribute pressure")
    st.markdown(
        """
Based on the spatial patterns of pressure and urban capacity, the thesis proposes a **DeTour**:
a corridor connecting underutilised but well-connected areas (e.g., **Sloterdijk — Zuidas — Bijlmer ArenA**).

The goal is to **reduce pressure on the historic core** by offering alternative, accessible destinations — while strengthening
a multi-core structure of the city.
        """.strip()
    )

    st.subheader("Key visuals")
    # Use your existing visuals if present
    safe_image("public transport corridor.png")
    safe_image("dining cafes.png")

    st.subheader("Why it makes sense (in 3 bullets)")
    st.markdown(
        """
- **Accessibility:** strong public transport connections enable easy re-routing.
- **Capacity potential:** parts of the corridor show higher network capacity / accessibility indicators (see Page 2).
- **Experience diversification:** encourages a broader distribution of visitor experiences across the city.
        """.strip()
    )

    # Optional: simple “core highlight” map (heuristic by name match)
    st.markdown("#### Optional: quick core highlight map")
    try:
        gdf = load_neighbourhood_polygons().copy()
        core_keywords = ["sloterdijk", "zuidas", "bijlmer", "arena", "amstel"]
        gdf["is_core"] = gdf["name"].astype(str).str.lower().apply(lambda s: any(k in s for k in core_keywords))
        gdf["fill_color"] = gdf["is_core"].apply(lambda x: [220, 80, 80, 160] if x else [170, 170, 170, 40])
        pydeck_geojson_map(gdf, tooltip_fields=["name"], zoom=11.5)
        st.caption("This is a simple name-keyword highlight. If you want exact polygons for the corridor, we can add a corridor layer later.")
    except Exception as e:
        st.info(f"Could not render optional map: {e}")


def page_about():
    st.title("About")
    st.markdown(
        """
**Isamu Goiati**  
MSc Urban Planning & Design (TU Delft) — graduated July 2025.

If you’re seeing this dashboard via a shared link and want to collaborate (urban data / mobility / tourism),
feel free to reach out.
        """.strip()
    )

    st.markdown("**Recommended links to add before posting on LinkedIn:**")
    st.code(
        "- Thesis PDF: <link>\n- Dashboard link: <link>\n- GitHub repo: <link>\n- LinkedIn: <link>"
    )


# ------------------------------------------------------------
# Navigation (public-ready: only what you want to show)
# ------------------------------------------------------------
st.sidebar.title("DeTourism Dashboard")
st.sidebar.caption("Public demo")

PAGES = {
    "Home": page_home,
    "Carrying Capacity": page_carrying_capacity,
    "The DeTour": page_detour,
    "About": page_about,
}

selection = st.sidebar.selectbox("Navigate", list(PAGES.keys()))
PAGES[selection]()
