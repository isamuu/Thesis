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
from folium import IFrame, Choropleth, Marker, LayerControl
from streamlit.components.v1 import html as st_html
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import os
import io
import contextily as ctx
from folium.plugins import MarkerCluster

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
    
    base = Path(__file__).resolve().parent
    image_path = base / "new Title heatmap.png"

    if image_path.exists():
        st.image(Image.open(image_path), use_container_width=True)
    else:
        st.warning("Image not found: new Title heatmap.png")

    
    st.markdown("""
    **Introduction**  
    Tourism is an essential part of Amsterdam’s economy and identity, but in recent years it has also become a growing source of pressure on everyday urban life. 
    Crowded streets, rising nuisance, and uneven spatial use reveal that overtourism is not just a question of how many visitors the city receives, 
    but where and when they concentrate.This dashboard accompanies my MSc thesis (TU Delft, 2025) and explores overtourism as a spatial–temporal urban system. 
    By combining digital traces of tourist activity with urban and network characteristics, the project aims to better understand how tourism pressure unfolds 
    across the city and how it might be redistributed more intelligently.""")
    
    # Resolve path to image
    base = Path(__file__).resolve().parent
    image_path = base / "SCWX2243.jpeg"

    if image_path.exists():
        st.image(Image.open(image_path), use_container_width=True)
    else:
        st.warning("Image not found: SCWX2243.jpeg")

    st.markdown("""
    The map below visualizes tourist pressure across Amsterdam at specific moments in time. It is constructed using publicly available data sources such as 
    Google Reviews and Popular Times, which act as proxies for where tourist activity is likely to concentrate. Each point represents a location associated 
    with visitor activity. The intensity of the heatmap reflects the relative level of pressure at that location for the selected day, hour, and activity category. 
    By adjusting the filters, you can explore how pressure shifts:
    between weekdays and weekends,
    across different times of day,
    and between different types of places (e.g. dining, culture, nightlife).
    Rather than treating tourism as a static total number, this approach reveals tourism as a dynamic pattern moving through the city, highlighting both 
    persistent hotspots and moments of peak intensity.
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
    st.subheader("Pressure Over Time (with composition)")
    
    ts_data = data[data["category"].isin(selected_cats)].copy()
    ts_data["datetime"] = pd.to_datetime(ts_data["datetime"], errors="coerce")
    
    # Mean pressure per category per timestamp
    by_cat = (
        ts_data.groupby(["datetime", "category"], as_index=False)["pressure"]
        .mean()
    )
    
    # Total pressure per timestamp (sum of category means)
    total = (
        by_cat.groupby("datetime", as_index=False)["pressure"]
        .sum()
        .rename(columns={"pressure": "total_pressure"})
    )
    
    base = alt.Chart(by_cat).encode(
        x=alt.X("datetime:T", title="Day of week", axis=alt.Axis(format="%a", tickCount=7))
    )
    
    area = base.mark_area().encode(
        y=alt.Y("pressure:Q", title="Pressure", scale=alt.Scale(domain=[0, 13.5])),
        color=alt.Color("category:N", title="Category"),
        tooltip=[
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("category:N", title="Category"),
            alt.Tooltip("pressure:Q", title="Category pressure", format=".2f"),
        ],
    )
    
    line = alt.Chart(total).mark_line(strokeWidth=2).encode(
        x="datetime:T",
        y=alt.Y("total_pressure:Q", scale=alt.Scale(domain=[0, 4])),
        tooltip=[
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("total_pressure:Q", title="Total pressure", format=".2f"),
        ],
    )
    
    chart = (area + line).properties(height=300).interactive()
    st.altair_chart(chart, use_container_width=True)




    


    st.markdown("""
    **Dashboard**  
    Use the navigation (top left) to explore how and where pressure becomes most intense, how urban structure relates to these patterns, 
    and how alternative spatial strategies can contribute to a more balanced and livable Amsterdam. This dashboard gives a glimpse of the thesis, 
    to see the full project go to the link on DeTourism page!""")
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
    st.title("Tourist flows")
            # Create two columns
    col1, col2 = st.columns([1.5, 1])  # Adjust width ratio as needed

    with col1:
        st.markdown("""
        **Understanding the Problem**  
        The current strategies lack a systemic view. Overtourism is not just about too many tourists, it's about when and where they move, 
        how the urban fabric absorbs them, and what social thresholds are crossed. While tourist pressure shows where activity concentrates, 
        this page focuses on how tourists move through the city. Using an edge-bundling technique, the visualization below aggregates thousands of individual movement paths into a coherent flow structure.
        Instead of showing every route separately, edge bundling reveals the dominant corridors that tourists repeatedly use to travel between places. This makes it possible to see how tourism relies on specific direction and how pressure is distributed along the urban network rather than confined to isolated hotspots.
        The result is a structural view of tourism flows: where movement converges, which routes act as key connectors, and where alternative paths could help redistribute activity.
        """)

    with col2:
        base = Path(__file__).resolve().parent
        image_path = base / "dining cafes.png"
        if image_path.exists():
            st.image(Image.open(image_path), use_container_width=True)
        else:
            st.warning("Image not found: dining cafes.png")
    

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
    st.title("Carrying Capacity — Urban Capacity Around Hotels")

    st.markdown(
    """
This page explores carrying capacity: the extent to which different parts of Amsterdam can accommodate tourist
activity without creating excessive pressure on everyday urban life.

Rather than focusing on where tourists currently concentrate, this analysis looks at where tourism could be
absorbed, based on urban structure, accessibility, and the spatial context of hotels.
    """.strip()
    )

    st.markdown(
    """
All indicators shown here are derived from hotel locations in the city and their surrounding urban environment.
Hotels are used as anchoring points because they represent key entry points into the tourism system and strongly
influence how visitors move, cluster, and spread through urban space.
    """.strip()
    )

    st.markdown("---")

    st.subheader("How the Map Works")

    st.markdown(
    """
The map displays values that have been calculated from different types of analyses.

- Use the dropdown menu to switch between different variables.
- Red colour indicates higher value, Green colour indicates lower value.
- Click on a point to see the exact value.

The goal is not to label areas as *“good”* or *“bad”*, but to compare spatial patterns of capacity, accessibility,
and potential pressure across the city.
    """.strip()
    )

    st.markdown("---")

    st.subheader("Understanding the Variables")

    st.markdown(
    """
The variables available in the dropdown can be grouped into three main categories. Each group highlights a different
aspect of urban capacity around hotels.
    """.strip()
)

    with st.expander("1. Accessibility & Network Centrality (Angular Choice)"):
        st.markdown(
        """
**Variables**
- 5min % high A.C.
- 15min % high A.C.
- 25min % high A.C.

These indicators show the share of highly central streets (Angular Choice) within a travel-time catchment around
hotels.

Angular Choice is a Space Syntax measure that approximates how likely a street is to be used as part of movement through
the city. Higher values indicate better network connectivity and accessibility.

The different time thresholds represent different spatial scales:
- **5 minutes:** very local accessibility
- **15 minutes:** district-scale movement
- **25 minutes:** city-wide connectivity
        """.strip()
                    )

    with st.expander("2. Tourist Pressure Around Hotels"):
        st.markdown(
        """
**Variables**
- pressure 5min
- pressure 15min
- pressure 25min

These variables represent aggregated tourist pressure signals within increasing travel-time catchments around
hotels.

They are derived from publicly available digital traces of tourist activity and indicate how intense tourism-related
activity is in the surroundings of hotel locations.

Together, they show how pressure accumulates and scales spatially around hotels.
        """.strip()
            )


    with st.expander("3. Coverage & Reach of Tourist Activity"):
        st.markdown(
        """
**Variables**
- total_points
- within_5min / within_15min / within_25min
- percent_within_5min / percent_within_15min / percent_within_25min

These variables describe **how much tourist activity falls within hotel catchments**.

- `within_*` counts how many activity points fall inside a given travel-time range.
- `percent_within_*` expresses this as a share of all points.
- `total_points` represents the total number of activity points associated with a neighbourhood.

They help contextualize accessibility and pressure by showing **how concentrated or dispersed activity is** around
hotels.
        """.strip()
    )

    st.markdown("---")

    st.markdown(
    """
**How to use this page**

Use this page to compare different spatial scales, identify areas with high accessibility but lower pressure, and
explore where the urban structure suggests latent capacity for tourism.

Rather than prescribing solutions, this analysis provides the spatial evidence needed to reason about where tourism
might be redistributed more sustainably.
    """.strip()
        )



    # 1) Load & parse geometry
    csv_path = Path(__file__).resolve().parent / "hotels_all_data.csv"
    df = pd.read_csv(csv_path)
    df["geometry"] = df["geometry"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    # 2) Extract coordinates for plotting
    gdf["lat"] = gdf.geometry.y
    gdf["lon"] = gdf.geometry.x

    # 3) Choose variable to visualize
    numeric_cols = gdf.select_dtypes(include='number').columns.tolist()
    show_cols = [col for col in numeric_cols if col not in ['lat', 'lon', 'Unnamed: 0'] and gdf[col].nunique() > 5]

    if not show_cols:
        st.warning("No suitable numeric columns available for visualization.")
        return

    selected_var = st.selectbox("Choose variable to display:", show_cols)

    # 4) Setup Folium map
    center = [gdf["lat"].mean(), gdf["lon"].mean()]
    m = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")
    cluster = MarkerCluster().add_to(m)

    # Normalize selected variable values for coloring
    vmin, vmax = gdf[selected_var].min(), gdf[selected_var].max()

    colormap = folium.LinearColormap(["green", "yellow", "red"], vmin=vmin, vmax=vmax)
    colormap.caption = selected_var
    colormap.add_to(m)

    for _, row in gdf.iterrows():
        value = row[selected_var]
        popup = f"<b>{row.get('name', 'Unnamed')}</b><br>{selected_var}: {value:.2f}"
        folium.CircleMarker(
            location=(row["lat"], row["lon"]),
            radius=5,
            color=colormap(value),
            fill=True,
            fill_opacity=0.7,
            popup=popup
        ).add_to(cluster)

    # 5) Display
    st_folium(m, width=900, height=600)


def page_detourism():
    def _find_asset(filename: str) -> Path:
        base = Path(__file__).resolve().parent
    
        candidates = [
            base / filename,
            base.parent / filename,
    
            base / "images" / filename,
            base.parent / "images" / filename,
    
            base / "assets" / filename,
            base.parent / "assets" / filename,
    
            base / "figures" / filename,
            base.parent / "figures" / filename,
        ]
    
        for p in candidates:
            if p.exists():
                return p
    
        # Helpful debug (shows where looked)
        raise FileNotFoundError(
            f"Could not find '{filename}'. Looked in:\n" + "\n".join(str(c) for c in candidates)
        )
    
    def _image_bytes(filename: str) -> bytes:
        """
        Reads image bytes so st.image() doesn't need to open a file path.
        """
        path = _find_asset(filename)
        try:
            return path.read_bytes()
        except Exception as e:
            st.error(f"Found '{filename}' at {path}, but couldn't read it: {e}")
            raise

    REPORT_URL = "https://repository.tudelft.nl/file/File_6c37c232-04ab-4e5a-9ccf-766005dcf32b?preview=1"
    st.title("DeTourism")

    st.markdown(
        """
A small selection of visuals from my thesis **DeTourism**.
Click the button below the cover to open the full report.
"""
    )

    st.divider()

    left, right = st.columns([1, 1.2], gap="large")

    with left:
        st.image(_image_bytes("frontpage.jpg"), use_container_width=True)

        try:
            st.link_button("Open thesis report", REPORT_URL, use_container_width=True)
        except Exception:
            st.markdown(f"[Open thesis report]({REPORT_URL})")

    with right:
        st.subheader("Selected visuals")
        st.markdown(
            """
The visual below give an impression of the report.
"""
        )

    st.divider()

    c1, c2 = st.columns(2, gap="large")
    c3, _ = st.columns([1, 1], gap="large")

    with c1:
        st.image(_image_bytes("analyses.png"),
                 caption="Analyses – spatial-temporal patterns & pressure/capacity indicators",
                 use_container_width=True)

    with c2:
        st.image(_image_bytes("vision map.png"),
                 caption="Vision map – DeTourism corridor strategy",
                 use_container_width=True)

    with c3:
        st.image(_image_bytes("park.png"),
                 caption="History & experience – example of possible strategic intervention",
                 use_container_width=True)

def page_about():
    st.title("About / Contact")
    st.markdown("""
    **Isamu Goiati**  
    Urban Designer and Data Scientist   
    https://www.linkedin.com/in/isamu-goiati/  
    """)

# ——— Navigation ———
pages = {
    "Home": page_home,
    "Overtourism": page_overtourism,
    "Tourist Flows": page_tourism_dynamics,
    "Carrying Capacity": page_carrying_capacity,
    "DeTourism": page_detourism,
    "About / Contact": page_about
}

selection = st.sidebar.selectbox("Navigate to", list(pages.keys()))
pages[selection]()
