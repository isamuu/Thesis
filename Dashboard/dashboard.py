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
from PIL import Image
import os
import io
import contextily as ctx

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
              return gpd.read_parquet(pq)    # ← no engine= here
    raise FileNotFoundError(
        f"Could not find 'bundled_routes.parquet' in {candidates}"
    )

data = load_data()

# ——— Page Functions ———
def page_home():
    st_html("""<script>window.scrollTo(0, 0);</script>""", height=0)
    st.title("Welcome to the Overtourism Dashboard")

    st.markdown("""
    **Introduction**  
    Amsterdam is facing increasing pressure from overtourism. With a growing global middle class and low-cost travel options, more people than ever are visiting the city.  
    While tourism brings economic benefits, it also causes serious strain on local life—leading to overcrowded streets, rising nuisance, and an erosion of social cohesion. Despite efforts like crowd control and earlier closing times, the city continues to address only the symptoms, not the deeper causes.
    """)
    
    # Resolve path to image
    base = Path(__file__).resolve().parent
    image_path = base / "SCWX2243.jpeg"

    if image_path.exists():
        st.image(Image.open(image_path), use_container_width=True)
    else:
        st.warning("Image not found: SCWX2243.jpeg")

    st.markdown("""
    **Understanding the Problem**  
    The current strategies lack a systemic view. Overtourism is not just about too many tourists—it's about when and where they move, how the urban fabric absorbs them, and what social thresholds are crossed. Cities like Amsterdam need to move beyond reactive measures and embrace complexity.
    """)
    base = Path(__file__).resolve().parent
    image_path = base / "dining cafes.png"

    if image_path.exists():
        st.image(Image.open(image_path), use_container_width=True)
    else:
        st.warning("Image not found: dining cafes.png")

    st.markdown("""
    **Why This Dashboard**  
    This dashboard transforms publicly available data—like Google reviews and Popular Times—into spatial and temporal insights. It allows us to see tourism not as a static number, but as a dynamic system unfolding through the city’s streets and neighborhoods.  

    Use the tabs in the top left corner to explore the chapters and see where and when pressure is most intense, how the urban environment shapes this impact, and what strategies can help reimagine tourism for a more livable Amsterdam.
    """)
    base = Path(__file__).resolve().parent
    image_path = base / "public transport corridor.png"

    if image_path.exists():
        st.image(Image.open(image_path), use_container_width=True)
    else:
        st.warning("Image not found: public transport corridor.png")

def page_overtourism():
    st_html("""<script>window.scrollTo(0, 0);</script>""", height=0)
    st.title("Overtourism")
    st.markdown("""
    **What it’s about**  
    Amsterdam is increasingly affected by overtourism. With millions of visitors each year, the city faces growing pressure on its public spaces, cultural fabric, and liveability. Tourism is no longer confined to specific landmarks or high seasons—its presence is felt across neighborhoods and throughout the week.  
    While strategies have been introduced to manage the flow of tourists, they often treat symptoms rather than structural causes. There is a need to better understand *where*, *when*, and *how* tourism impacts the city.

    **Analysis performed**  
    To explore this, an analysis was conducted on publicly available texts from local media, neighborhood reports, and complaints. These texts were classified into different types—places, moments, and impacts—and mapped to specific neighborhoods.  
    A separate dataset was used to measure self-reported nuisance among residents.

    **Key findings**  
    - Tourism is still highly concentrated in the historic center, but pressure spreads outward to other neighborhoods  
    - Activity peaks on Friday and Saturday evenings and around public holidays  
    - Residents report increasing nuisance, loss of familiarity, and pressure on everyday life  
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
        st.markdown("""
        *This map shows where overtourism is often mentioned in local texts and reports.  
        Darker areas highlight neighborhoods that appear frequently in descriptions of tourist activity. Click on a neighborhood to read sample sentences from the sources.*
        """)
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
        st.markdown("""
        *This map shows the percentage of residents in each neighborhood who report experiencing nuisance due to tourism.  
        Darker red tones indicate higher levels of nuisance.*
        """)
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
    st.markdown("""
    *The charts below show when tourism-related activity is most often mentioned in texts.  
    Bars in **blue** highlight hours and days frequently associated with tourist pressure.*
    """)
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
    st.markdown("""
    *Tourism has a variety of impacts on the city. Click each icon to explore quotes related to nuisance, the economy, or loss of social familiarity.*
    """)
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
    **How to Explore Tourist Pressure**
    
    Use the panel on the left to filter and the map/time‐series on the right will update instantly:
    
    - **Categories**  
      Toggle one or more attraction types (e.g. Dining, Activities, Shops) to focus on specific flows.
    
    - **Day & Hour**  
      Pick a day of the week and hour of the day to see when and where pressure peaks.
    
    The **Tourist Pressure Map** renders a real‐time heatmap of aggregated “pressure” values at each location.  
    Below, **Pressure Over Time** shows the average pressure across your selected categories for every timestamp—so you can spot daily or weekly rhythms.
    """)


    # — Top layout: filters on the left, map on the right —
    filter_col, map_col = st.columns([1, 3])

    # 1) FILTER PANEL
    with filter_col:
        st.subheader("Filters")

        # a) Category — 3-column checkboxes
        categories = sorted(data['category'].unique())
        chk_cols = st.columns(3)
        selected_cats = []
        for idx, cat in enumerate(categories):
            c = chk_cols[idx % 3]
            if c.checkbox(cat, value=True, key=f"dyn_cat_{idx}"):
                selected_cats.append(cat)

        # b) Day selector
        filtered_for_days = data[data['category'].isin(selected_cats)]
        unique_days = sorted(filtered_for_days['datetime'].dt.date.unique())
        selected_day = st.selectbox(
            "Day",
            unique_days,
            format_func=lambda d: d.strftime("%A")
        )

        # c) Hour slider
        selected_hour = st.slider("Hour", 0, 23, 0)
        selected_dt = datetime.datetime.combine(selected_day,
                                                datetime.time(selected_hour))

    # 2) MAP PANEL
    with map_col:
        st.subheader("Tourist Pressure Map")
        subset = data[
            (data['category'].isin(selected_cats)) &
            (data['datetime'] == selected_dt)
        ]
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
            st.info("No data for that time/category combination.")

    # — Full-width time series below —
    st.subheader("Pressure Over Time")
    ts_data = data[data['category'].isin(selected_cats)]
    pressure_ts = (
        ts_data
        .groupby('datetime')['pressure']
        .mean()
        .reset_index()
        .set_index('datetime')
    )
    st.line_chart(pressure_ts)
    

    def create_animation(gdf: gpd.GeoDataFrame, fps: int = 10) -> bytes:
        """
        Manually build an in-memory GIF by capturing each frame from the Matplotlib canvas.
        """
        if gdf.crs.to_string() != "EPSG:3857":
            gdf_vis = gdf.to_crs(epsg=3857)
        else:
            gdf_vis = gdf.copy()
        # 2) Build coordinate lists & styling
        paths  = [np.array(line.coords) for line in gdf_vis.geometry]
        cats   = gdf_vis['category'].astype("category")
        visits = gdf_vis['visits'].values
    
        cmap      = plt.get_cmap("tab10")
        cat_colors = {c: cmap(i) for i, c in enumerate(cats.cat.categories)}
        lw        = np.interp(visits, [visits.min(), visits.max()], [0.5, 3.0])
    
        # 3) Set up figure & axes
        fig, ax = plt.subplots(figsize=(6,6), dpi=100)
        fig.patch.set_facecolor('black')
        ax.set_facecolor('black')
        ax.axis('off')
    
       
        # 4) Zoom to a fixed Amsterdam bbox (lon/lat 4.68–5.08, 52.28–52.44)
        from shapely.geometry import box
        # define in WGS84
        am_bbox = box(4.68, 52.28, 5.08, 52.44)
        # reproject to WebMercator (same CRS as gdf_vis)
        am_geo = gpd.GeoSeries([am_bbox], crs="EPSG:4326").to_crs(gdf_vis.crs)
        xmin, ymin, xmax, ymax = am_geo.total_bounds
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
    
        # 5) Add dark basemap
        ctx.add_basemap(
            ax,
            source=ctx.providers.CartoDB.DarkMatter,
            crs=gdf_vis.crs.to_string(),
            zoom=12
        )
    
        # 6) Draw in batches for speed
        chunk_size = 100
        n_edges    = len(paths)
        n_frames   = int(np.ceil(n_edges / chunk_size))
        frames     = []
    
        for fidx in range(n_frames):
            s = fidx * chunk_size
            e = min(s + chunk_size, n_edges)
            for i in range(s, e):
                p   = paths[i]
                col = cat_colors[gdf_vis['category'].iloc[i]]
                ax.plot(p[:,0], p[:,1], color=col, lw=lw[i], alpha=0.1)
    
            # capture PNG
            buf_png = io.BytesIO()
            fig.savefig(
                buf_png,
                format='png',
                facecolor=fig.get_facecolor(),
                bbox_inches='tight',
                pad_inches=0
            )
            buf_png.seek(0)
            frames.append(Image.open(buf_png).convert('RGB'))
    
        # 7) Assemble GIF
        gif_buf = io.BytesIO()
        duration = int(1000 / fps)
        frames[0].save(
            gif_buf,
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=duration
        )
        gif_buf.seek(0)
        plt.close(fig)
        return gif_buf
    
    # -------------------------------------------------------------------
    st.title("Edge‐Bundled Routes Animation")
    st.markdown("""
    **How to View Bundled Tourist Flows**
    
    This animation exposes the major corridors tourists follow by grouping (bundling) individual paths:
    
    1. **Category Filters**  
       Check the boxes to include only the types of trips you care about (e.g. Dining & Cafes, Activities, Cannabisshop).
    
    2. **Animation Speed**  
       Use the FPS slider to slow down or speed up the build-up of routes.
    
    3. **Generate**  
       Click **Generate Edge Animation** to render the GIF. Each frame draws a batch of bundled edges, revealing the dominant travel corridors through Amsterdam.
    
    Use the final animation to identify high-traffic pathways, plan detours, or understand overall flow structure in the city.
    """)
    # 1) load your bundled data (no text input needed)
    try:
        gdf = load_bundled_routes()
    except FileNotFoundError as e:
        st.error(str(e))
        return
    
    # 2) filter by category
    st.markdown("**Filter Categories**")
    categories = sorted(gdf['category'].unique())
    col1, col2 = st.columns(2)
    selected = []
    selected = []
    for idx, cat in enumerate(categories):
        container = col1 if idx % 2 == 0 else col2
        # Only pre-check the first category, uncheck the rest
        default_checked = True if idx == 0 else False
        if container.checkbox(cat, value=default_checked, key=f"cat_{idx}"):
            selected.append(cat)
    filtered = gdf[gdf['category'].isin(selected)].reset_index(drop=True)

    # 3) animation controls
    fps = st.slider("Frames per second", 1, 30, 10)

    if st.button("🎬 Generate Edge Animation"):
        with st.spinner("Rendering GIF…"):
            buf = create_animation(filtered, fps=fps)
            st.image(buf, caption="Edge-bundled flows", use_container_width=True)

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
