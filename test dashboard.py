import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import pydeck as pdk
import datetime
import altair as alt
import folium
from streamlit_folium import st_folium
from folium import IFrame
from streamlit.components.v1 import html as st_html

st.set_page_config(page_title="Digital Report Dashboard", layout="wide")

# ——— Data Loading ———
@st.cache_data
def load_data():
    df = pd.read_csv("test_pressure_time_small.csv")
    df.columns = df.columns.str.strip()
    df['geometry'] = df['geometry'].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    gdf['lat'], gdf['lon'] = gdf.geometry.y, gdf.geometry.x
    gdf = gdf.rename(columns={"Datetime": "datetime"})
    gdf['datetime'] = pd.to_datetime(gdf['datetime'])
    return gdf

@st.cache_data
def load_media_data():
    return pd.read_csv("media_analysis_sentences.csv", sep = ";")
@st.cache_data
def load_neighbourhoods():
    return gpd.read_file("amsterdam_neighbourhoods.geojson")

data = load_data()

# ——— Page Functions ———
def page_home():
    st.title("Welcome to the Overtourism Dashboard")
    st.markdown("""
    **Introduction**  
    This dashboard is the interactive, digital counterpart to the report on overtourism in Amsterdam.  
    It covers:
    - **Problematisation**: defining overtourism and its local impacts  
    - **Approach**: media content analysis, spatial‐temporal mapping, morphological & statistical modelling  
    """)

def page_overtourism():
    st.title("Overtourism")
    st.markdown("""
    **What it’s about**  
    Identifying current moments, places and impacts of overtourism in Amsterdam.

    **Analysis performed**  
    - Media content analysis of municipal documents, platforms, news articles & a 2016 documentary  
    - Statistical mapping of resident‐reported nuisance, drunkenness, social cohesion & unsafety per neighbourhood  

    *Key findings*  
    - Concentrated in the historic centre, spreading outward  
    - Peaks on Friday/Saturday evenings and holidays  
    - Erosion of social familiarity & local liveability
    """)
    media = load_media_data()

    # — Places Map ——
    st.subheader("Places")
    st.markdown("Hover or click a polygon to see the sentences that mention it.")
    
    # Load and filter
    neigh_gdf = load_neighbourhoods()  # your GeoJSON now has a 'level' column
    places_df = media[media.type == "place"]
    mentioned = places_df.neighbourhood.unique().tolist()
    
    # Split by level
    dist_gdf = neigh_gdf[
        (neigh_gdf["name"].isin(mentioned)) &
        (neigh_gdf["level"] == "District")
    ]
    neigh_only_gdf = neigh_gdf[
        (neigh_gdf["name"].isin(mentioned)) &
        (neigh_gdf["level"] == "Neighbourhood")
    ]
    
    # Build HTML pop-up content (with small wrapped text)
    popup_map = {}
    for n, grp in places_df.groupby("neighbourhood"):
        lines = ""
        for _, row in grp.iterrows():
            # wrap in a styled div
            lines += (
                f"<div style='font-size:12px; line-height:1.2; "
                f"white-space:normal; max-width:250px;'>"
                f"<b>{n}</b> {row.sentence}<br>"
                f"<i>({row.source})</i></div><hr style='margin:4px 0;'>"
            )
        popup_map[n] = lines
    
    # 1) Create a greyscale base map locked to Amsterdam
    m = folium.Map(
        location=[52.37, 4.90],
        zoom_start=12,
        min_zoom=11,       # can't zoom out past level 11
        max_zoom=15,       # can't zoom in past level 15
        max_bounds=True,   # can't pan outside initial bounds
        tiles="CartoDB positron"
    )
    
    # Style functions
    def style_district(feat):
        return {
            "fillColor": "#f34242",  # light green
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.3
        }
    
    def style_neighbourhood(feat):
        return {
            "fillColor": "#b20c0c",  # darker green
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.5
        }
    
    # 2) Add Districts behind
    for _, r in dist_gdf.iterrows():
        name = r["name"]
        iframe = IFrame(html=popup_map[name], width=270, height=150)
        popup = folium.Popup(iframe, max_width=300)
        folium.GeoJson(
            data=r.geometry.__geo_interface__,
            style_function=style_district,
            tooltip=folium.Tooltip(name, sticky=True),
            popup=popup
        ).add_to(m)
    
    # 3) Add Neighbourhoods on top
    for _, r in neigh_only_gdf.iterrows():
        name = r["name"]
        iframe = IFrame(html=popup_map[name], width=300, height=180)
        popup = folium.Popup(iframe, max_width=320)
        folium.GeoJson(
            data=r.geometry.__geo_interface__,
            style_function=style_neighbourhood,
            tooltip=folium.Tooltip(name, sticky=True),
            popup=popup
        ).add_to(m)
    
    # 4) Render full-width in Streamlit
    st_html(
        m._repr_html_(),
        width=None,    # let Streamlit stretch it to the container
        height=500,
        scrolling=True
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
    st.altair_chart(hour_chart, use_container_width=True)
    
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
    - Origin–destination isochrone analysis (5/15/25 min walks)  
    - Edge‐bundling of movement directions & activity‐combination networks  
    - Heatmaps of tourist pressure in space and time  
    """)
    st.subheader("Tourist Pressure Map")
    # — Filters —
    unique_days = sorted(data['datetime'].dt.date.unique())
    col1, col2 = st.columns(2)
    with col1:
        selected_day = st.selectbox("Select Day", unique_days)
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
    - Overlay of low‐pressure zones near hotel clusters with high‐capacity network & spatial indices  
    - Definition of three cores (Sloterdijk, Zuidas, Bijlmer ArenA) + inter‐core zones  
    - Uses Metro line 50 as backbone  
    """)

def page_strategising_detour():
    st.title("Strategising a DeTour")
    st.markdown("""
    **What it’s about**  
    High‐level strategy to implement the DeTour, aligned with Amsterdam’s polycentric vision.

    **Content**  
    - Stakeholder coordination & phased roll‐out  
    - Policy measures & incentive design  
    - Monitoring & evaluation framework  
    """)

def page_about():
    st.title("About / Contact")
    st.markdown("""
    **Your Name**  
    MSc Urban Planning & Design student at XYZ University  
    Email: your.email@example.com  
    LinkedIn: linkedin.com/in/yourprofile  
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
