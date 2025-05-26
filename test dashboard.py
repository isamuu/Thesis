import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import pydeck as pdk
import datetime

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
