import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import pydeck as pdk
import datetime
import time

# Load and prepare your data
@st.cache_data
def load_data():
    df = pd.read_csv("test_pressure_time_small.csv")
    df.columns = df.columns.str.strip()  # Clean any extra whitespace in column names
    df['geometry'] = df['geometry'].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    gdf['lat'] = gdf.geometry.y
    gdf['lon'] = gdf.geometry.x
    gdf = gdf.rename(columns = {"Datetime":"datetime"})
    gdf['datetime'] = pd.to_datetime(gdf['datetime'])
    return gdf

data = load_data()

# Get unique days in the dataset (as Python date objects)
unique_days = sorted(data['datetime'].dt.date.unique())

# Create two separate widgets for day and hour selection
col1, col2 = st.columns(2)
with col1:
    selected_day = st.selectbox("Select Day", unique_days, index=0)
with col2:
    selected_hour = st.slider("Select Hour", min_value=0, max_value=23, value=0)

# Combine selected day and hour to form the full datetime
selected_datetime = datetime.datetime.combine(selected_day, datetime.time(selected_hour))

# Initialize session state for play functionality if not already set
if "playing" not in st.session_state:
    st.session_state.playing = False
if "play_index" not in st.session_state:
    st.session_state.play_index = 0




# Filter data for the selected datetime
data_selected = data[data['datetime'] == selected_datetime]

st.subheader("Tourist Pressure Map")
if not data_selected.empty:
    # Set up a view state centered around the current data points
    view_state = pdk.ViewState(
        latitude=data_selected['lat'].mean(),
        longitude=data_selected['lon'].mean(),
        zoom=12,
        pitch=0
    )
    # Create a HeatmapLayer using the pressure values as weights
    heatmap_layer = pdk.Layer(
        "HeatmapLayer",
        data=data_selected,
        get_position="[lon, lat]",
        get_weight="pressure",
        radiusPixels=60
    )
    deck = pdk.Deck(layers=[heatmap_layer], initial_view_state=view_state)
    st.pydeck_chart(deck)
else:
    st.write("No data available for the selected time.")

st.subheader("Pressure Over Time")
# Aggregate pressure values over time (using mean, for example) for a line chart
pressure_over_time = data.groupby('datetime')['pressure'].mean().reset_index().sort_values("datetime")
pressure_over_time = pressure_over_time.set_index("datetime")
st.line_chart(pressure_over_time)

