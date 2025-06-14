import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import pydeck as pdk
import datetime
import altair as alt
import folium
import branca
from streamlit_folium import st_folium
from folium import IFrame
from streamlit.components.v1 import html as st_html
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import os

st.set_page_config(page_title="Digital Report Dashboard", layout="wide")

# ——— Data Loading ———
@st.cache_data
def load_data():
    # folder where this script lives (e.g. .../Dashboard)
    base = Path(__file__).resolve().parent

    # try both Dashboard/ and its parent (repo root)
    candidates = [
        base / "test_pressure_time_small.csv",
        base.parent / "test_pressure_time_small.csv",
    ]

    for csv_path in candidates:
        if csv_path.exists():
            break
    else:
        raise FileNotFoundError(
            f"Could not find 'test_pressure_time_small.csv' in {candidates}"
        )

    # load & clean
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df['geometry'] = df['geometry'].apply(wkt.loads)

    # make GeoDataFrame
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    gdf['lat'], gdf['lon'] = gdf.geometry.y, gdf.geometry.x

    # normalize datetime
    gdf = gdf.rename(columns={"Datetime": "datetime"})
    gdf['datetime'] = pd.to_datetime(gdf['datetime'])

    
    return gdf

@st.cache_data
def load_media_data():
    base = Path(__file__).resolve().parent

    # look in Dashboard/ then repo root
    candidates = [
        base / "media_analysis_sentences.csv",
        base.parent / "media_analysis_sentences.csv",
    ]
    for csv_path in candidates:
        if csv_path.exists():
            break
    else:
        raise FileNotFoundError(f"Could not find 'media_analysis_sentences.csv' in {candidates}")

    return pd.read_csv(csv_path, sep=";")
@st.cache_data
def load_neighbourhoods():
    base = Path(__file__).resolve().parent

    candidates = [
        base / "amsterdam_neighbourhoods.geojson",
        base.parent / "amsterdam_neighbourhoods.geojson",
    ]
    for geojson_path in candidates:
        if geojson_path.exists():
            break
    else:
        raise FileNotFoundError(f"Could not find 'amsterdam_neighbourhoods.geojson' in {candidates}")

    return gpd.read_file(geojson_path)
@st.cache_data
def load_nuisance_data():
    # folder containing this script (e.g. .../Dashboard)
    base = Path(__file__).resolve().parent

    # two places we might have put the CSV
    candidates = [
        base / "overtourism_neighbourhoods.csv",
        base.parent / "overtourism_neighbourhoods.csv",
    ]

    # pick the first one that exists
    for csv_path in candidates:
        if csv_path.exists():
            break
    else:
        raise FileNotFoundError(
            f"Could not find 'overtourism_neighbourhoods.csv' in {candidates}"
        )

    # load and convert to GeoDataFrame
    df = pd.read_csv(csv_path)
    df["geometry"] = df["geometry"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    return gdf

@st.cache_data
def load_bundled_routes():
    """
    Look for bundled_routes.parquet in the Dashboard folder or its parent,
    then load with GeoPandas.
    """
    base = Path(__file__).resolve().parent
    candidates = [
        base / "bundled_routes.parquet",
        base.parent / "bundled_routes.parquet",
    ]
    for pq in candidates:
        if pq.exists():
            return gpd.read_parquet(pq, engine="pyarrow")
    raise FileNotFoundError(
        f"Could not find 'bundled_routes.parquet' in {candidates}"
    )

data = load_data()

# ——— Page Functions ———
def page_home():
    st.title("Welcome to the Overtourism Dashboard")
    st.markdown("""
    **Introduction**  
    This dashboard is the interactive, digital counterpart to the report on overtourism in Amsterdam.  
    It covers:
    - ... 
    """)

def page_overtourism():
    st.title("Overtourism")
    st.markdown("""
    **What it’s about**  
    ...

    **Analysis performed**  
    - ... 

    *Key findings*  
    - Concentrated in the historic centre, spreading outward  
    - Peaks on Friday/Saturday evenings and holidays  
    - Erosion of social familiarity & local liveability
    """)
    # — Data & Popups —
    media      = load_media_data()
    neigh_gdf  = load_neighbourhoods()
    places_df  = media[media.type == "place"]

    # build pop-up HTML per neighbourhood
    popup_map = {}
    for name, grp in places_df.groupby("neighbourhood"):
        html = ""
        for _, row in grp.iterrows():
            html += (
                f"<div style='font-size:12px; line-height:1.2; "
                f"white-space:normal; max-width:250px;'>"
                f"<b>{name}</b> {row.sentence}<br>"
                f"<i>({row.source})</i></div><hr style='margin:4px 0;'>"
            )
        popup_map[name] = html

    # split districts vs neighbourhoods
    mentioned     = places_df.neighbourhood.unique().tolist()
    dist_gdf      = neigh_gdf.query("name in @mentioned and level=='District'")
    neigh_only_gdf= neigh_gdf.query("name in @mentioned and level=='Neighbourhood'")

    # nuisance data
    nuis_gdf = load_nuisance_data().query("level=='Neighbourhood' and pct_nuisance==pct_nuisance")

    # style functions
    def style_district(feat):
        return {
            "fillColor": "#fcbba1",  # light red
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.3
        }

    def style_neighbourhood(feat):
        return {
            "fillColor": "#cb181d",  # dark red
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.5
        }

    def style_nuisance(feat):
        val = feat["properties"].get("pct_nuisance")
        if val is None:
            return {"fillColor":"#cccccc","color":"black","weight":1,"fillOpacity":0.3}
        return {"fillColor":cmap(val),"color":"black","weight":1,"fillOpacity":0.7}

    # prepare the nuisance colormap
    # — prepare the nuisance colormap for right map (white → dark red) —
    vmax = nuis_gdf["pct_nuisance"].max()
    cmap = branca.colormap.LinearColormap(
        ["white", "#cb181d"],
        vmin=0,
        vmax=vmax,
        caption="% Residents Experiencing Nuisance"
    )
    st.subheader("Places")

    col1, col2 = st.columns(2)

    
    # Left: Overtourism Places map
    with col1:
        m1 = folium.Map(
            location=[52.37, 4.90],
            zoom_start=12, min_zoom=11, max_zoom=15, max_bounds=True,
            tiles="CartoDB positron"
        )
        for _, r in dist_gdf.iterrows():
            iframe = IFrame(html=popup_map[r["name"]], width=270, height=150)
            folium.GeoJson(
                data=r.geometry.__geo_interface__,
                style_function=style_district,
                tooltip=folium.Tooltip(r["name"], sticky=True),
                popup=folium.Popup(iframe, max_width=300)
            ).add_to(m1)
        for _, r in neigh_only_gdf.iterrows():
            iframe = IFrame(html=popup_map[r["name"]], width=300, height=180)
            folium.GeoJson(
                data=r.geometry.__geo_interface__,
                style_function=style_neighbourhood,
                tooltip=folium.Tooltip(r["name"], sticky=True),
                popup=folium.Popup(iframe, max_width=320)
            ).add_to(m1)
        st_html(m1._repr_html_(), width=None, height=400, scrolling=False)

    # Right: Tourism Nuisance continuous map (white → dark red, semi-transparent)
    with col2:
        # 1) Base map
        m2 = folium.Map(
            location=[52.37, 4.90],
            zoom_start=12, min_zoom=11, max_zoom=15, max_bounds=True,
            tiles="CartoDB positron"
        )

        # 2) Continuous GeoJson layer styled by our colormap
        folium.GeoJson(
            data=nuis_gdf.__geo_interface__,
            style_function=lambda feat: {
                "fillColor": cmap(feat["properties"]["pct_nuisance"]),
                "color": "black",
                "weight": 1,
                "fillOpacity": 0.7
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["name", "pct_nuisance"],
                aliases=["Neighbourhood", "% Nuisance"],
                localize=True
            )
        ).add_to(m2)


        # 4) Embed full-width, no scrollbar
        st_html(
            m2._repr_html_(),
            width=None,
            height=400,
            scrolling=False
        )

    # — Moments Graphs ——
    st.subheader("Moments")
    st.markdown("Bars in **blue** are hours/days mentioned in the texts. Hover to read the sentences.")
    moments = media[media.type == "moment"]
    
    # prepare hours
    hrs = (moments.groupby("hour")
                   .sentence
                   .apply(lambda s: "<br>".join(s))
                   .reset_index(name="sentences"))
    hrs["count"] = hrs.sentences.str.count("<br>") + 1
    full_hrs = pd.DataFrame({"hour": list(range(24))})
    hrs = full_hrs.merge(hrs, on="hour", how="left").fillna({"sentences":"", "count":0})
    
    hour_chart = (
        alt.Chart(hrs)
           .mark_bar()
           .encode(
             x=alt.X("hour:O", title="Hour of Day"),
             y=alt.Y("count:Q", title="Mentions"),
             color=alt.condition(
               alt.datum.count > 0,
               alt.value("steelblue"),
               alt.value("lightgray")
             ),
             tooltip=[
               alt.Tooltip("hour:O", title="Hour"),
               alt.Tooltip("sentences:N", title="Sentences")
             ]
           )
           .properties(width=600, height=200)
    )
    
    
    # prepare days
    days_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    dys = (moments.groupby("day")
                   .sentence
                   .apply(lambda s: "<br>".join(s))
                   .reset_index(name="sentences"))
    dys["count"] = dys.sentences.str.count("<br>") + 1
    full_days = pd.DataFrame({"day": days_order})
    dys = full_days.merge(dys, on="day", how="left").fillna({"sentences":"", "count":0})
    
    day_chart = (
        alt.Chart(dys)
           .mark_bar()
           .encode(
             x=alt.X("day:O", sort=days_order, title="Day of Week"),
             y=alt.Y("count:Q", title="Mentions"),
             color=alt.condition(
               alt.datum.count > 0,
               alt.value("steelblue"),
               alt.value("lightgray")
             ),
             tooltip=[
               alt.Tooltip("day:O", title="Day"),
               alt.Tooltip("sentences:N", title="Sentences")
             ]
           )
           .properties(width=600, height=200)
    )
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**By Hour of Day**")
        st.altair_chart(hour_chart, use_container_width=True)
    
    with col2:
        st.markdown("**By Day of Week**")
        st.altair_chart(day_chart, use_container_width=True)

    # — Impacts Icons ——
    st.subheader("Impacts")
    st.markdown("Click an icon to read all related sentences.")
    impacts = media[media.type == "impact"].groupby("impact_type").sentence.apply(list).to_dict()
    cols = st.columns(3)
    icons = {"nuisance":"😡", "economy":"💰", "familiarity":"🤝"}
    for col, imp in zip(cols, impacts):
        with col:
            with st.expander(f"{icons[imp]} {imp.title()}"):
                for s in impacts[imp]:
                    st.write(f"- {s}")

def page_tourism_dynamics():
    st.title("Tourism Dynamics")
    st.markdown("""
    **What it’s about**  
    Exploring spatio‐temporal flows of tourists via a continuous “pressure” metric derived from Google Maps Popular Times and review counts.

    **Analysis performed**  
    - ...  
    """)
    st.subheader("Tourist Pressure Map")
    # — Filters —
    unique_days = sorted(data['datetime'].dt.date.unique())
    col1, col2 = st.columns(2)
    with col1:
        selected_day = st.selectbox(
            "Select Day",
            unique_days,
            format_func=lambda d: d.strftime("%A")  # show “Monday”, “Tuesday”, etc.
        )
    with col2:
        selected_hour = st.slider("Select Hour", 0, 23, 0)

    selected_dt = datetime.datetime.combine(selected_day, datetime.time(selected_hour))

    # — Data subset & map —
    subset = data[data['datetime'] == selected_dt]
    if not subset.empty:
        view = pdk.ViewState(
            latitude=subset['lat'].mean(),
            longitude=subset['lon'].mean(),
            zoom=12, pitch=0
        )
        layer = pdk.Layer(
            "HeatmapLayer",
            data=subset,
            get_position="[lon, lat]",
            get_weight="pressure",
            radiusPixels=60
        )
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view))
    else:
        st.info("No data for this time.")

    st.subheader("Pressure Over Time")
    pressure_ts = data.groupby('datetime')['pressure'].mean().reset_index().set_index('datetime')
    st.line_chart(pressure_ts)

    def create_animation(gdf: gpd.GeoDataFrame, fps: int = 10, dpi: int = 100):
        """
        Build a GIF in memory that draws each bundled edge sequentially.
        Returns: bytes buffer containing the GIF.
        """
        # Prepare coordinate sequences
        paths = [np.array(line.coords) for line in gdf.geometry]
        cats  = gdf['category'].astype("category")
        visits = gdf['visits'].values
    
        # Create a color map for categories
        cmap = plt.get_cmap("tab10")
        cat_colors = {cat: cmap(i) for i, cat in enumerate(cats.cat.categories)}
    
        # Scale line‐width by visits (optional)
        min_v, max_v = visits.min(), visits.max()
        lw = np.interp(visits, [min_v, max_v], [0.5, 3.0])
    
        fig, ax = plt.subplots(figsize=(6,6))
        fig.patch.set_facecolor('black')
        ax.set_facecolor('black')
        ax.axis('off')
    
        # Compute bounding box from data
        xs = np.concatenate([p[:,0] for p in paths])
        ys = np.concatenate([p[:,1] for p in paths])
        pad = 0.01
        ax.set_xlim(xs.min() - pad, xs.max() + pad)
        ax.set_ylim(ys.min() - pad, ys.max() + pad)
    
        lines_drawn = []  # to keep references so they stay on the canvas
    
        def update(frame):
            # draw the next segment
            p = paths[frame]
            cat = gdf['category'].iloc[frame]
            line_obj, = ax.plot(p[:,0], p[:,1],
                                color=cat_colors[cat],
                                lw=lw[frame],
                                alpha=0.8)
            lines_drawn.append(line_obj)
            return [line_obj]
    
        ani = FuncAnimation(
            fig, update,
            frames=len(paths),
            blit=False,
            interval=200  # milliseconds between frames
        )
    
        buf = io.BytesIO()
        ani.save(buf, writer='pillow', fps=fps, dpi=dpi)
        buf.seek(0)
        plt.close(fig)
        return buf
    
    # -------------------------------------------------------------------
    st.title("Edge‐Bundled Routes Animation")
    
    # 1) Load your bundled data
    data_path = st.sidebar.text_input("Path to bundled GeoDataFrame", "bundled_routes.geojson")
    if not os.path.exists(data_path):
        st.sidebar.error(f"File not found: {data_path}")
        st.stop()
    
    gdf = load_bundled(data_path)
    
    # 2) Category filter
    all_cats = list(gdf['category'].unique())
    selected = st.sidebar.multiselect("Filter by category", all_cats, default=all_cats)
    filtered = gdf[gdf['category'].isin(selected)].reset_index(drop=True)
    
    st.sidebar.markdown(f"👉 {len(filtered)} / {len(gdf)} edges selected")
    
    # 3) Animation parameters
    fps = st.sidebar.slider("Frames per second", 1, 30, 10)
    dpi = st.sidebar.slider("Output DPI", 50, 200, 100)
    
    if st.sidebar.button("🎬 Generate Animation"):
        with st.spinner("Rendering GIF... this may take a moment"):
            buf = create_animation(filtered, fps=fps, dpi=dpi)
            st.image(buf, caption="Edge‐bundled routes animation", use_column_width=True)

def page_carrying_capacity():
    st.title("Carrying Capacity")
    st.markdown("""
    **What it’s about**  
    Assessing how spatial network capacity and land‐use form modify liveability under tourism pressure.

    **Analysis performed**  
    - Space Syntax Angular Choice  
    - Floor Space Index (FSI), Ground Space Index (GSI), Mixed‐Use Index (MXI)  
    - Moderation analysis: tourist pressure → perceived nuisance, moderated by private/pedestrian/built space  
    """)

def page_finding_detour():
    st.title("Finding a DeTour")
    st.markdown("""
    **What it’s about**  
    Selecting & delineating a “DeTour” corridor through under‐utilised districts to redistribute flows.

    **Analysis performed**  
    - ... 
    """)

def page_strategising_detour():
    st.title("Strategising a DeTour")
    st.markdown("""
    **What it’s about**  
    ...
    """)

def page_about():
    st.title("About / Contact")
    st.markdown("""
    **Isamu Goiati**  
    MSc Urban Planning & Design student at TU Delft  
    """)

# ——— Navigation ———
pages = {
    "Home": page_home,
    "Analysis: Overtourism": page_overtourism,
    "Analysis: Tourism Dynamics": page_tourism_dynamics,
    "Analysis: Carrying Capacity": page_carrying_capacity,
    "Finding a DeTour": page_finding_detour,
    "Strategising a DeTour": page_strategising_detour,
    "About / Contact": page_about
}

selection = st.sidebar.selectbox("Navigate to", list(pages.keys()))
pages[selection]()
