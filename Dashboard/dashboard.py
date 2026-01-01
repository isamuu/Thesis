# De-Tourism – LinkedIn-ready Streamlit dashboard
# ---------------------------------------------------
# Run:
#   pip install -r requirements.txt
#   streamlit run dashboard_linkedin.py
#
# Expected files (same folder as this script, or one level up):
#   - hotels_all_data.csv
#   - overtourism_neighbourhoods.csv
#   - bundled_routes.parquet   (optional but recommended; requires pyarrow)
#
# Notes:
# - This version intentionally focuses on 4 shareable pages:
#   1) Home (project intro + tourist-pressure map)
#   2) Tourism dynamics (edge-bundled routes)
#   3) Carrying capacity (neighbourhood choropleths + variable selector)
#   4) The De-Tour (strategy summary + simple corridor map)

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import wkt

import streamlit as st
import pydeck as pdk
import folium
import branca
from streamlit_folium import st_folium


# -----------------------------
# Page config + simple styling
# -----------------------------
st.set_page_config(
    page_title="De-Tourism | Dashboard",
    page_icon="🧭",
    layout="wide",
)

st.markdown(
    """
<style>
/* tighten layout a bit */
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
/* nicer section headers */
h1, h2, h3 {letter-spacing: -0.02em;}
/* make sidebar look cleaner */
section[data-testid="stSidebar"] {padding-top: 0.5rem;}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# Data loading helpers
# -----------------------------
def _find_file(filename: str) -> Path:
    """Look in current folder and one level up."""
    base = Path(__file__).resolve().parent
    candidates = [base / filename, base.parent / filename]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Could not find '{filename}' in: {candidates}")


@st.cache_data(show_spinner=False)
def load_hotels() -> pd.DataFrame:
    """
    Hotel point dataset (place-based pressure metrics).
    We use POINT geometry to extract lon/lat for the heatmap.
    """
    csv_path = _find_file("hotels_all_data.csv")
    df = pd.read_csv(csv_path)

    # Extract lon/lat from the POINT WKT in the 'geometry' column
    # (fallback: try 'WKT_LNG_LAT' if needed)
    geom_col = "geometry" if "geometry" in df.columns else "WKT_LNG_LAT"
    pts = df[geom_col].astype(str).apply(wkt.loads)
    df["lon"] = pts.apply(lambda p: float(p.x))
    df["lat"] = pts.apply(lambda p: float(p.y))

    # Ensure expected numeric columns exist (coerce where possible)
    num_cols = [
        "pressure 5min", "pressure 15min", "pressure 25min",
        "5min % high A.C.", "15min % high A.C.", "25min % high A.C.",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


@st.cache_data(show_spinner=False)
def load_neighbourhood_polygons() -> gpd.GeoDataFrame:
    """
    Neighbourhood polygons + perceived nuisance (%), as provided in
    overtourism_neighbourhoods.csv (geometry is WKT polygons).
    """
    csv_path = _find_file("overtourism_neighbourhoods.csv")
    df = pd.read_csv(csv_path)

    if "geometry" not in df.columns:
        raise ValueError("overtourism_neighbourhoods.csv must contain a 'geometry' WKT column.")

    gdf = gpd.GeoDataFrame(
        df.drop(columns=["geometry"]),
        geometry=df["geometry"].astype(str).apply(wkt.loads),
        crs="EPSG:4326",
    )
    return gdf


@st.cache_data(show_spinner=False)
def load_bundled_routes() -> gpd.GeoDataFrame | None:
    """
    Edge-bundled routes. Optional.
    Requires pyarrow to be available (in requirements.txt).
    """
    try:
        pq_path = _find_file("bundled_routes.parquet")
    except FileNotFoundError:
        return None

    try:
        # In your own environment, pyarrow should be installed via requirements.txt
        gdf = gpd.read_parquet(pq_path)
        if gdf.crs is None:
            # Most route datasets are stored in lon/lat; set as a sensible default.
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        return gdf
    except Exception as e:
        st.warning(
            "Could not load bundled_routes.parquet. "
            "If you want the Tourism Dynamics page, make sure pyarrow is installed "
            "(pip install pyarrow) and the parquet file is present.\n\n"
            f"Error: {e}"
        )
        return None


@st.cache_data(show_spinner=False)
def neighbourhood_summary() -> gpd.GeoDataFrame:
    """
    Merge neighbourhood polygons with aggregated hotel-based indicators.
    We join on the 'name' field in polygons to the 'Wijk' field in hotels.
    """
    poly = load_neighbourhood_polygons()
    hotels = load_hotels()

    if "Wijk" not in hotels.columns:
        # Still return polygons only
        return poly

    agg = hotels.groupby("Wijk", dropna=False).agg(
        hotels_count=("place_id", "count"),
        pressure_5=("pressure 5min", "mean"),
        pressure_15=("pressure 15min", "mean"),
        pressure_25=("pressure 25min", "mean"),
        ac_5=("5min % high A.C.", "mean"),
        ac_15=("15min % high A.C.", "mean"),
        ac_25=("25min % high A.C.", "mean"),
    ).reset_index().rename(columns={"Wijk": "name"})

    merged = poly.merge(agg, on="name", how="left")
    return merged


# -----------------------------
# Reusable map components
# -----------------------------
def render_pressure_heatmap(hotels: pd.DataFrame) -> None:
    """
    A LinkedIn-friendly, fast, interactive heatmap (pydeck).
    """
    st.subheader("Tourist pressure map")

    c1, c2, c3 = st.columns([1.2, 1.2, 1.2])

    with c1:
        metric = st.selectbox(
            "Indicator",
            options=[
                "pressure 15min",
                "pressure 5min",
                "pressure 25min",
                "15min % high A.C.",
                "5min % high A.C.",
                "25min % high A.C.",
            ],
            index=0,
        )
    with c2:
        cat_col = "Combined Category 15min" if "Combined Category 15min" in hotels.columns else None
        if cat_col:
            cats = ["All"] + sorted([c for c in hotels[cat_col].dropna().unique().tolist()])
            selected_cat = st.selectbox("Hotel context (category)", options=cats, index=0)
        else:
            selected_cat = "All"
    with c3:
        intensity = st.slider("Intensity", min_value=0.5, max_value=6.0, value=2.0, step=0.5)

    df = hotels.copy()
    if selected_cat != "All" and cat_col:
        df = df[df[cat_col] == selected_cat]

    # Keep only rows with the selected metric available
    df = df[np.isfinite(df[metric].astype(float))]
    if df.empty:
        st.info("No data for the current selection.")
        return

    # View state centered on the selected points
    view = pdk.ViewState(
        latitude=float(df["lat"].mean()),
        longitude=float(df["lon"].mean()),
        zoom=11.7,
        pitch=0,
    )

    layer = pdk.Layer(
        "HeatmapLayer",
        data=df,
        get_position="[lon, lat]",
        get_weight=metric,
        radius_pixels=55,
        intensity=intensity,
        threshold=0.03,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="mapbox://styles/mapbox/light-v11",
        tooltip={"text": "{name}\n" + metric + ": {" + metric + "}"},
    )

    st.pydeck_chart(deck, use_container_width=True)

    st.caption(
        "This map visualises hotel-related pressure indicators. "
        "Weights are derived from the selected metric and rendered as a heat intensity surface."
    )


def render_neighbourhood_choropleth(gdf: gpd.GeoDataFrame, value_col: str, title: str, fmt: str = ".2f") -> None:
    """
    Choropleth with Folium (clean, report-like look).
    """
    st.subheader(title)

    # Prepare a safe copy
    mdf = gdf.copy()
    if value_col not in mdf.columns:
        st.info(f"Column '{value_col}' not available in the merged neighbourhood dataset.")
        return

    # Folium expects EPSG:4326
    if mdf.crs is None:
        mdf = mdf.set_crs("EPSG:4326", allow_override=True)
    else:
        mdf = mdf.to_crs("EPSG:4326")

    # Handle missing values
    vals = pd.to_numeric(mdf[value_col], errors="coerce")
    if vals.notna().sum() == 0:
        st.info("No values available for this variable (all missing).")
        return

    vmin, vmax = float(vals.min()), float(vals.max())
    colormap = branca.colormap.linear.YlOrRd_09.scale(vmin, vmax)
    colormap.caption = value_col

    def style_fn(feature):
        name = feature["properties"].get("name")
        row = mdf.loc[mdf["name"] == name]
        v = None
        if not row.empty:
            v = row.iloc[0][value_col]
        if pd.isna(v):
            return {"fillOpacity": 0.0, "weight": 0.4, "color": "#999999"}
        return {
            "fillColor": colormap(float(v)),
            "color": "#3a3a3a",
            "weight": 0.6,
            "fillOpacity": 0.75,
        }

    # Map
    m = folium.Map(location=[52.37, 4.90], zoom_start=11.7, tiles="CartoDB positron")

    folium.GeoJson(
        data=mdf.__geo_interface__,
        name="Neighbourhoods",
        style_function=style_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["name", value_col],
            aliases=["Neighbourhood", title],
            localize=True,
            sticky=True,
            labels=True,
            toLocaleString=False,
        ),
        highlight_function=lambda x: {"weight": 2.0, "fillOpacity": 0.85},
    ).add_to(m)

    colormap.add_to(m)
    st_folium(m, width=None, height=560)


# -----------------------------
# Pages
# -----------------------------
def page_home():
    st.title("De-Tourism")
    st.markdown(
        "<div style='font-size:1.15rem; margin-top:-0.3rem;'>"
        "<b>Exploring spatial-temporal dimensions to mitigate over-tourism and enhance urban livability</b>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
**What this is**  
This dashboard is a compact, shareable version of my thesis work on overtourism in Amsterdam.  
It combines multiple open data sources and spatial analyses to explore **where pressure concentrates**, **how it shifts**, and **what urban form can do** to mitigate negative impacts.

**How to use it**  
Use the map below to explore “tourist pressure” indicators. Then navigate to:
- **Tourism Dynamics** → edge-bundled movement patterns
- **Carrying Capacity** → neighbourhood comparisons across variables
- **The De-Tour** → a corridor-based strategy to redistribute pressure
"""
    )

    st.divider()

    hotels = load_hotels()
    render_pressure_heatmap(hotels)


def page_tourism_dynamics():
    st.title("Tourism Dynamics")
    st.markdown(
        """
This page highlights **movement patterns** through the city as **edge-bundled routes** (a visual technique that makes
recurring corridors stand out clearly). It’s designed to be visually compelling and easy to understand at a glance.
"""
    )

    routes = load_bundled_routes()
    if routes is None or routes.empty:
        st.info("bundled_routes.parquet not available (or couldn’t be loaded). Add the file + pyarrow to enable this page.")
        return

    # Choose a sensible weight column if present
    weight_candidates = ["weight", "count", "n", "value", "flow", "trips"]
    weight_col = next((c for c in weight_candidates if c in routes.columns), None)

    # Optional filters if time columns exist
    day_col = next((c for c in ["day", "weekday", "Day"] if c in routes.columns), None)
    hour_col = next((c for c in ["hour", "Hour"] if c in routes.columns), None)

    df = routes.copy()
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if day_col:
            days = ["All"] + sorted([str(x) for x in df[day_col].dropna().unique().tolist()])
            day_choice = st.selectbox("Day", options=days, index=0)
        else:
            day_choice = "All"
    with c2:
        if hour_col:
            hours = ["All"] + sorted([int(x) for x in df[hour_col].dropna().unique().tolist()])
            hour_choice = st.selectbox("Hour", options=hours, index=0)
        else:
            hour_choice = "All"
    with c3:
        max_lines = st.slider("Max routes to draw", min_value=300, max_value=6000, value=2500, step=250)

    if day_col and day_choice != "All":
        df = df[df[day_col].astype(str) == str(day_choice)]
    if hour_col and hour_choice != "All":
        df = df[df[hour_col].astype(int) == int(hour_choice)]

    # Prefer strongest routes for clarity
    if weight_col:
        df = df.sort_values(weight_col, ascending=False)

    df = df.head(int(max_lines)).copy()
    df = df.to_crs("EPSG:4326")

    # Build a GeoJSON object for pydeck
    geojson = df.__geo_interface__

    # View state: Amsterdam center
    view = pdk.ViewState(latitude=52.37, longitude=4.90, zoom=11.5, pitch=0)

    # Line width scaling
    if weight_col:
        w = pd.to_numeric(df[weight_col], errors="coerce").fillna(0)
        # avoid extreme widths
        w_scaled = (w - w.min()) / (w.max() - w.min() + 1e-9)
        df["_width"] = 1 + 5 * w_scaled
        geojson = df.__geo_interface__
        width_expr = "properties._width"
    else:
        width_expr = 1.5

    line_layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        stroked=True,
        filled=False,
        get_line_width=width_expr,
        get_line_color=[20, 20, 20],  # charcoal
        line_width_min_pixels=1,
        pickable=True,
    )

    deck = pdk.Deck(
        layers=[line_layer],
        initial_view_state=view,
        map_style="mapbox://styles/mapbox/light-v11",
        tooltip={"text": "Route"},
    )

    st.pydeck_chart(deck, use_container_width=True)

    with st.expander("Optional: export a simple GIF (fast mode)", expanded=False):
        st.markdown(
            """
This quick export is meant to create a short, lightweight animation you can attach to a LinkedIn post.
If your parquet includes **hour** (and optionally **day**), it will render a small sequence.
"""
        )

        if not hour_col:
            st.info("No hour column detected in routes → GIF export disabled.")
        else:
            gif_day = None
            if day_col:
                gif_day = st.selectbox(
                    "GIF day",
                    options=sorted([str(x) for x in routes[day_col].dropna().unique().tolist()]),
                    index=0,
                )
            hour_range = st.slider("Hours", min_value=0, max_value=23, value=(10, 22))
            n_frames = st.slider("Frames", min_value=6, max_value=24, value=12, step=2)

            export = st.button("Render GIF")
            if export:
                import matplotlib.pyplot as plt
                from PIL import Image
                import io

                hrs = np.linspace(hour_range[0], hour_range[1], int(n_frames)).astype(int).tolist()
                frames: list[Image.Image] = []

                base_df = routes.copy()
                if day_col and gif_day is not None:
                    base_df = base_df[base_df[day_col].astype(str) == str(gif_day)]

                base_df = base_df.to_crs("EPSG:4326")

                # Pre-calc bounds for consistent framing
                minx, miny, maxx, maxy = base_df.total_bounds
                padx, pady = (maxx - minx) * 0.05, (maxy - miny) * 0.05

                for h in hrs:
                    sdf = base_df[base_df[hour_col].astype(int) == int(h)]
                    if weight_col:
                        sdf = sdf.sort_values(weight_col, ascending=False).head(2000)
                    else:
                        sdf = sdf.head(2000)

                    fig, ax = plt.subplots(figsize=(6.5, 6.5), dpi=130)
                    ax.set_xlim(minx - padx, maxx + padx)
                    ax.set_ylim(miny - pady, maxy + pady)
                    ax.axis("off")
                    ax.set_title(f"Amsterdam | hour {h:02d}:00", fontsize=12)

                    if not sdf.empty:
                        sdf.plot(ax=ax, linewidth=0.6, alpha=0.7)

                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.05)
                    plt.close(fig)
                    buf.seek(0)
                    frames.append(Image.open(buf).convert("P", palette=Image.ADAPTIVE))

                out = io.BytesIO()
                frames[0].save(
                    out,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=140,
                    loop=0,
                )
                out.seek(0)

                st.download_button(
                    "Download GIF",
                    data=out.getvalue(),
                    file_name="detourism_routes.gif",
                    mime="image/gif",
                )
                st.success("GIF ready.")


def page_carrying_capacity():
    st.title("Carrying Capacity")
    st.markdown(
        """
This page compares neighbourhoods using a **variable selector** and a clean **choropleth map**.
It’s designed to look closer to report-style maps (no point heatmap), while still being interactive.

**Interpretation tip:** these are *neighbourhood-level* aggregates—use them to compare patterns, not as precise measurements per street.
"""
    )

    gdf = neighbourhood_summary()

    # Variable selector (shareable + coherent)
    options = {
        "Perceived nuisance (% residents, 2023)": ("pct_nuisance", ".1f"),
        "Avg tourist pressure (15 min)": ("pressure_15", ".2f"),
        "Avg tourist pressure (5 min)": ("pressure_5", ".2f"),
        "Avg tourist pressure (25 min)": ("pressure_25", ".2f"),
        "Avg % high Angular Choice (15 min)": ("ac_15", ".2f"),
        "Avg % high Angular Choice (5 min)": ("ac_5", ".2f"),
        "Avg % high Angular Choice (25 min)": ("ac_25", ".2f"),
        "Hotel count (as proxy intensity)": ("hotels_count", ".0f"),
    }

    choice = st.selectbox("Select variable", options=list(options.keys()), index=0)
    col, fmt = options[choice]

    render_neighbourhood_choropleth(gdf, col, title=choice, fmt=fmt)


def page_detour():
    st.title("The De-Tour 🧭")
    st.markdown(
        """
The **De-Tour** proposes a corridor-based strategy to redistribute tourist flows from the historic core to a belt of
well-connected areas that can absorb visitors while strengthening local economies and protecting everyday liveability.

**Core idea**
- Create a **connected sequence of destinations** (not a single new “attraction”)
- Use **mobility + walkability** to make the corridor feel like one coherent experience
- Combine **high capacity** areas with **lower current tourist pressure**
"""
    )

    st.subheader("A simple corridor sketch (for sharing)")
    st.caption("This is a lightweight visual placeholder you can refine later—kept intentionally simple for LinkedIn sharing.")

    # Hard-coded hubs (can be edited)
    hubs = [
        {"name": "Sloterdijk", "lat": 52.389, "lon": 4.838},
        {"name": "Vondelpark / Oud-Zuid", "lat": 52.357, "lon": 4.868},
        {"name": "Zuidas", "lat": 52.338, "lon": 4.873},
        {"name": "Bijlmer ArenA", "lat": 52.312, "lon": 4.944},
    ]

    m = folium.Map(location=[52.365, 4.90], zoom_start=11.6, tiles="CartoDB positron")

    # Draw corridor polyline
    folium.PolyLine([(h["lat"], h["lon"]) for h in hubs], weight=5, opacity=0.8).add_to(m)

    # Mark hubs
    for h in hubs:
        folium.CircleMarker(
            location=(h["lat"], h["lon"]),
            radius=7,
            fill=True,
            fill_opacity=0.9,
            popup=h["name"],
        ).add_to(m)

    st_folium(m, width=None, height=520)

    st.markdown(
        """
**Want to cite / dive deeper?**  
Add a link in your LinkedIn post to your thesis PDF and/or repository, and point readers to:
- the **Tourist pressure** page (immediate “wow”)
- the **Tourism Dynamics** page (edge-bundled routes)
- this **De-Tour** page (clear takeaway + strategy)
"""
    )


# -----------------------------
# Navigation
# -----------------------------
PAGES = {
    "Home": page_home,
    "Tourism Dynamics": page_tourism_dynamics,
    "Carrying Capacity": page_carrying_capacity,
    "The De-Tour": page_detour,
}

with st.sidebar:
    st.markdown("### Navigation")
    selection = st.radio("", list(PAGES.keys()), index=0)

    st.markdown("---")
    st.markdown("**Tip for LinkedIn:**")
    st.markdown("- Screenshot the Home map + export a GIF from Tourism Dynamics.")
    st.markdown("- Add a short story + 2–3 concrete findings.")

PAGES[selection]()
